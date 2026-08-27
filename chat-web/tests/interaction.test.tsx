import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AskUserQuestionForm } from "@/components/chat/blocks/ToolQuestionCardsBlock";
import { createInitialChatRuntimeState, reduceChatEvents, upsertInteractions } from "@/lib/event-reducer";
import { SparkHttpClient } from "@/lib/api/http-client";
import { SparkInteractionApi } from "@/lib/api/interaction-api";
import type { PendingInteractionDTO } from "@/types/interaction";
import { RUN_ID, THREAD_ID } from "@/fixtures/chat/scenarios";
import type { ChatEventEnvelope } from "@/types/chat";

const pending: PendingInteractionDTO = {
  run_id: RUN_ID,
  interaction_id: "33333333-3333-3333-3333-333333333333",
  interaction_key: `run:${RUN_ID}:tool:call_ask_1:stage:0`,
  kind: "ask_user",
  status: "pending",
  tool_call_id: "call_ask_1",
  tool_name: "ask_user",
  tool_version: "v1",
  schema_version: 2,
  question_ids: ["q1"],
  request: {
    intro: "需要更多信息",
    questions: [
      {
        id: "q1",
        header: "时间范围",
        prompt: "分析几天？",
        options: [{ label: "7 天" }, { label: "30 天" }],
        multi_select: false,
        allow_free_text: true,
      },
    ],
  },
  expires_at: "2026-08-28T00:00:00Z",
};

const base = { run_id: RUN_ID, thread_id: THREAD_ID, payload_version: 1 } as const;

function event(type: string, sequence: number, payload: Record<string, unknown>): ChatEventEnvelope {
  return { ...base, type, event_id: `00000000-0000-0000-0000-0000000001${sequence}`, sequence, timestamp: "2026-08-27T02:00:00Z", payload };
}

describe("AskUserQuestionForm", () => {
  it("requires a choice before submit, then locks and emits index+label pairs", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue({ ok: true });
    render(<AskUserQuestionForm interaction={pending} onSubmit={onSubmit} />);
    const submit = screen.getByRole("button", { name: "提交" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: "30 天" }));
    expect(submit).toBeEnabled();
    await user.click(submit);
    expect(onSubmit).toHaveBeenCalledWith([
      { question_id: "q1", selected_option_indexes: [1], selected_labels: ["30 天"], free_text: "" },
    ]);
  });

  it("locks controls while submitting and shows a resolved summary", async () => {
    const user = userEvent.setup();
    let resolveSubmit: (value: unknown) => void = () => undefined;
    const onSubmit = vi.fn().mockImplementation(() => new Promise((resolve) => { resolveSubmit = resolve; }));
    const { rerender } = render(<AskUserQuestionForm interaction={pending} submitting={false} onSubmit={onSubmit} />);
    await user.click(screen.getByRole("radio", { name: "7 天" }));
    await user.click(screen.getByRole("button", { name: "提交" }));
    rerender(<AskUserQuestionForm interaction={pending} submitting onSubmit={onSubmit} />);
    expect(screen.getByRole("button", { name: "提交中…" })).toBeDisabled();
    resolveSubmit({ ok: true });
    rerender(
      <AskUserQuestionForm
        interaction={{ ...pending, status: "resolved" }}
        answersPreview={[{ question_id: "q1", selected_option_indexes: [0], selected_labels: ["7 天"] }]}
      />,
    );
    expect(screen.getByText("已确认")).toBeInTheDocument();
    expect(screen.getByText("7 天")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交" })).not.toBeInTheDocument();
  });

  it("renders expired and cancelled copy without a submit control", () => {
    const { rerender } = render(<AskUserQuestionForm interaction={{ ...pending, status: "expired" }} />);
    expect(screen.getByText("已过期")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交" })).not.toBeInTheDocument();
    rerender(<AskUserQuestionForm interaction={{ ...pending, status: "cancelled" }} />);
    expect(screen.getByText("已取消")).toBeInTheDocument();
  });

  it("surfaces a 409/410 error from the submit path", () => {
    render(<AskUserQuestionForm interaction={pending} error="这个问题已经回答过了。" onSubmit={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("这个问题已经回答过了。");
  });
});

describe("interaction reducer", () => {
  it("stores one interaction per id and updates the same entry across terminal events", () => {
    const requested = event("interaction.requested", 1, { interaction: pending });
    const waiting = event("run.waiting", 2, { status: "waiting_for_user_input", interaction_id: pending.interaction_id });
    let state = reduceChatEvents(createInitialChatRuntimeState(), [requested, waiting]);
    expect(state.runsById[RUN_ID].status).toBe("waiting_for_user_input");
    expect(state.interactionsByRun[RUN_ID][pending.interaction_id].status).toBe("pending");
    state = reduceChatEvents(state, [
      event("interaction.resolved", 3, { interaction_id: pending.interaction_id, interaction: { ...pending, status: "resolved" } }),
      event("run.resumed", 4, { interaction_id: pending.interaction_id }),
    ]);
    expect(Object.keys(state.interactionsByRun[RUN_ID])).toEqual([pending.interaction_id]);
    expect(state.interactionsByRun[RUN_ID][pending.interaction_id].status).toBe("resolved");
    expect(state.runsById[RUN_ID].status).toBe("queued");
  });

  it("merges REST pending recovery without duplicating the card identity", () => {
    const state = upsertInteractions(createInitialChatRuntimeState(), RUN_ID, [pending, pending]);
    expect(Object.keys(state.interactionsByRun[RUN_ID])).toEqual([pending.interaction_id]);
  });

  it("marks cancelled from interaction.cancelled", () => {
    const state = reduceChatEvents(createInitialChatRuntimeState(), [
      event("interaction.requested", 1, { interaction: pending }),
      event("interaction.cancelled", 2, { interaction_id: pending.interaction_id, interaction: { ...pending, status: "cancelled" } }),
    ]);
    expect(state.interactionsByRun[RUN_ID][pending.interaction_id].status).toBe("cancelled");
  });
});

describe("SparkInteractionApi", () => {
  it("sends Idempotency-Key and wraps answers in response", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const http = new SparkHttpClient({
      baseUrl: "https://spark.test",
      fetcher: async (input, init) => {
        calls.push({ url: String(input), init });
        return new Response(JSON.stringify({ code: 0, msg: "accepted", data: { interaction: pending, run: { id: RUN_ID, status: "queued", last_sequence: 4 } } }), { status: 202 });
      },
    });
    const api = new SparkInteractionApi(http);
    await api.getPendingForRun(RUN_ID);
    await api.submitResponse(pending.interaction_id, {
      run_id: RUN_ID,
      interaction_key: pending.interaction_key,
      schema_version: 2,
      answers: [{ question_id: "q1", selected_option_indexes: [0], selected_labels: ["7 天"] }],
    }, "idem-1");
    expect(calls[0].url).toContain(`/runs/${RUN_ID}/interactions/pending/`);
    expect(new Headers(calls[1].init?.headers).get("Idempotency-Key")).toBe("idem-1");
    expect(JSON.parse(String(calls[1].init?.body))).toEqual({
      response: {
        run_id: RUN_ID,
        interaction_key: pending.interaction_key,
        schema_version: 2,
        answers: [{ question_id: "q1", selected_option_indexes: [0], selected_labels: ["7 天"] }],
      },
    });
  });
});
