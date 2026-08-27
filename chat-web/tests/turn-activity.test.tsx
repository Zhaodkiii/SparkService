import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TurnActivity } from "@/components/chat/turn/TurnActivity";
import { projectTurnActivity } from "@/lib/chat/turn-activity-projector";
import type { TurnActivityInput } from "@/lib/chat/turn-activity-projector";
import type { ToolActivityDTO } from "@/types/tool";
import type { TurnTraceNode } from "@/types/chat";

function tool(overrides: Partial<ToolActivityDTO> = {}): ToolActivityDTO {
  return {
    tool_call_id: "call_1",
    name: "query_member_profile",
    version: "v1",
    display_name: "读取健康档案",
    target: "server",
    status: "completed",
    round_index: 0,
    call_index: 0,
    revision: 1,
    display_args: {},
    result_preview: null,
    source_refs: [],
    error: null,
    duplicate_of: null,
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

function activity(overrides: Partial<TurnActivityInput> = {}) {
  return projectTurnActivity({ runId: "run_1", runStatus: "running", assistantStatus: null, toolRows: [], contentStreaming: false, ...overrides });
}

function toolNode(a: ToolActivityDTO): TurnTraceNode {
  return { kind: "tool", tool: a };
}

describe("TurnActivity", () => {
  it("auto-folds on entering the composing phase, before the Run reaches a terminal status", () => {
    const node = toolNode(tool());
    const { container, rerender } = render(
      <TurnActivity activity={activity({ runStatus: "running" })} thinkingBlocks={[]} traceNodes={[node]} />,
    );
    expect(container.querySelector(".turn-activity--open")).toBeTruthy();
    rerender(<TurnActivity activity={activity({ runStatus: "running", contentStreaming: true })} thinkingBlocks={[]} traceNodes={[node]} />);
    expect(container.querySelector(".turn-activity--open")).toBeFalsy();
  });

  it("does not render a chevron when running with no trace or thinking", () => {
    render(<TurnActivity activity={activity({ runStatus: "running" })} thinkingBlocks={[]} traceNodes={[]} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("小鲸探索中…");
  });

  it("shows a ticking elapsed duration while running, using startedAt", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-26T00:00:05Z"));
    const node = toolNode(tool());
    render(<TurnActivity activity={activity({ runStatus: "running" })} thinkingBlocks={[]} traceNodes={[node]} startedAt="2026-08-26T00:00:00Z" />);
    expect(document.querySelector(".turn-activity__duration")?.textContent).toMatch(/·/);
    vi.useRealTimers();
  });

  it("freezes the duration on the server-confirmed value once terminal", () => {
    const node = toolNode(tool());
    render(<TurnActivity activity={activity({ runStatus: "completed" })} thinkingBlocks={[]} traceNodes={[node]} durationMs={4500} startedAt="2026-08-26T00:00:00Z" />);
    expect(screen.getByText("· 4.5s")).toBeInTheDocument();
    expect(document.querySelector(".turn-activity--running")).toBeFalsy();
  });

  it("shows a completed header for historical turns even without trace", () => {
    render(<TurnActivity activity={activity({ runStatus: "completed" })} thinkingBlocks={[]} traceNodes={[]} durationMs={8000} />);
    expect(screen.getByRole("status")).toHaveTextContent("已完成");
    expect(screen.getByText("· 8s")).toBeInTheDocument();
  });

  it("defaults to expanded for failed turns", () => {
    const node = toolNode(tool({ status: "failed" }));
    const { container } = render(<TurnActivity activity={activity({ runStatus: "failed" })} thinkingBlocks={[]} traceNodes={[node]} durationMs={3000} />);
    expect(container.querySelector(".turn-activity--open")).toBeTruthy();
    expect(screen.getByText("生成失败")).toBeInTheDocument();
  });
});
