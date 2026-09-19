import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AssistantTurn } from "@/components/chat/turn/AssistantTurn";
import type { ChatBlockDTO } from "@/types/chat";

function block(overrides: Partial<ChatBlockDTO> & { id: string; kind: string }): ChatBlockDTO {
  return {
    status: "ready",
    revision: 1,
    order_key: 1,
    node_role: "timeline",
    payload: {},
    ...overrides,
  };
}

describe("AssistantTurn", () => {
  it("does not render a fixed assistant avatar", () => {
    const { container } = render(
      <AssistantTurn
        messageId="m1"
        blocks={[block({ id: "t", kind: "text", payload: { text: { _0: "你好" } } })]}
        turnSummary={{ run_id: "r1", status: "completed", started_at: "2026-08-26T00:00:00Z", finished_at: "2026-08-26T00:00:08Z", duration_ms: 8000, regenerate_allowed: true, delete_allowed: true, usage: null }}
      />,
    );
    expect(container.querySelector(".message__avatar")).toBeNull();
    expect(container.querySelectorAll(".turn-activity__state").length).toBe(1);
    expect(container.textContent).toContain("已完成");
  });

  it("renders symptom collection as one summary card without tool activity or model advice", () => {
    const { container } = render(
      <AssistantTurn
        messageId="symptom-message"
        blocks={[
          block({ id: "thought", kind: "deepThought", payload: { deep_thought: { _0: "模型正在推理" } } }),
          block({ id: "text", kind: "text", payload: { text: { _0: "建议立即前往急诊并完成进一步检查" } } }),
          block({ id: "tool-call", kind: "toolCall", payload: { tool_call: { _0: { name: "collect_symptoms", arguments: "{\"action\":\"review\"}" } } } }),
          block({
            id: "summary",
            kind: "symptomCollectionCard",
            payload: {
              symptom_collection_card: {
                _0: {
                  collection_id: "collection-1",
                  task_status: "completed",
                  snapshot: {
                    collection_id: "collection-1",
                    status: "completed",
                    analysis_summary: "主要不适为头晕，今天出现，伴恶心。",
                    primary_complaint: "头晕",
                    onset_time: "今天刚出现",
                    required_fields: ["primary_complaint", "onset_time"],
                  },
                },
              },
            },
          }),
          block({
            id: "questions",
            kind: "toolQuestionCards",
            payload: {
              tool_question_cards: {
                _0: [{
                  id: "round-1",
                  status: "submitted",
                  prompt: {
                    symptom_collection_id: "collection-1",
                    questions: [{ id: "q1", question: "持续多久？", selection_mode: "single", options: [{ id: "today", text: "今天" }] }],
                  },
                  answers: [{ question_id: "q1", selected_option_ids: ["today"] }],
                }],
              },
            },
          }),
        ]}
        turnSummary={{ run_id: "r2", status: "completed", started_at: "2026-09-19T00:00:00Z", finished_at: "2026-09-19T00:00:08Z", duration_ms: 8000, regenerate_allowed: true, delete_allowed: true, usage: null }}
      />,
    );

    expect(container.querySelectorAll("[data-testid='symptom-collection-card']")).toHaveLength(1);
    expect(container.textContent).toContain("症状信息汇总");
    expect(container.textContent).toContain("问诊进度 100%");
    expect(container.textContent).toContain("主要不适为头晕，今天出现，伴恶心。");
    expect(container.textContent).not.toContain("建议立即前往急诊");
    expect(container.textContent).not.toContain("模型正在推理");
    expect(container.textContent).not.toContain("持续多久");
    expect(container.textContent).not.toContain("问答记录");
    expect(container.querySelector(".turn-activity")).toBeNull();
  });
});
