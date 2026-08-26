import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TurnActivity } from "@/components/chat/turn/TurnActivity";
import { projectTurnActivity } from "@/lib/chat/turn-activity-projector";
import type { TurnActivityInput } from "@/lib/chat/turn-activity-projector";
import type { ToolActivityDTO } from "@/types/tool";
import type { TurnTraceNode } from "@/types/chat";

// Feature flags are read from `process.env` once at module load, so toggling
// them per-test needs a mock. `vi.hoisted` avoids the TDZ error that a plain
// top-level `let` would hit (vi.mock's factory runs while the module graph
// loads, before the test file's own statements execute), and the getter
// keeps the binding live across renders (TurnActivity re-reads it every
// render) without `vi.resetModules`, which would otherwise risk loading a
// second React copy mid-test.
const flagState = vi.hoisted(() => ({ deepTutorUiEnabled: false }));
vi.mock("@/lib/feature-flags", () => ({
  get CHAT_DEEPTUTOR_TURN_UI_ENABLED() { return flagState.deepTutorUiEnabled; },
  CHAT_SMOOTH_STREAM_ENABLED: false,
  CHAT_TOOL_UI_ENABLED: false,
  CHAT_TOOL_SETTINGS_ENABLED: false,
}));

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

afterEach(() => {
  flagState.deepTutorUiEnabled = false;
});

describe("TurnActivity — legacy renderer (flag off)", () => {
  it("only folds once the whole Run is terminal (no auto-fold on entering composing)", () => {
    const node = toolNode(tool());
    const { rerender } = render(
      <TurnActivity activity={activity({ runStatus: "running", contentStreaming: true })} thinkingBlocks={[]} traceNodes={[node]} />,
    );
    expect(document.querySelector(".turn-activity--open")).toBeTruthy();
    rerender(<TurnActivity activity={activity({ runStatus: "completed" })} thinkingBlocks={[]} traceNodes={[node]} durationMs={1200} />);
    expect(document.querySelector(".turn-activity--open")).toBeFalsy();
    expect(document.querySelector(".turn-activity")).toBeTruthy();
  });

  it("keeps the expand shell even when running with an empty trace", () => {
    render(<TurnActivity activity={activity({ runStatus: "running" })} thinkingBlocks={[]} traceNodes={[]} />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded");
  });
});

describe("TurnActivity — DeepTutor renderer (flag on)", () => {
  it("auto-folds on entering the composing phase, before the Run reaches a terminal status", () => {
    flagState.deepTutorUiEnabled = true;
    const node = toolNode(tool());
    const { container, rerender } = render(
      <TurnActivity activity={activity({ runStatus: "running" })} thinkingBlocks={[]} traceNodes={[node]} />,
    );
    expect(container.querySelector(".turn-activity--open")).toBeTruthy();
    rerender(<TurnActivity activity={activity({ runStatus: "running", contentStreaming: true })} thinkingBlocks={[]} traceNodes={[node]} />);
    expect(container.querySelector(".turn-activity--open")).toBeFalsy();
  });

  it("tightens expandability: a running turn with no trace/thinking has no chevron", () => {
    flagState.deepTutorUiEnabled = true;
    render(<TurnActivity activity={activity({ runStatus: "running" })} thinkingBlocks={[]} traceNodes={[]} />);
    const button = screen.getByRole("button");
    expect(button).not.toHaveAttribute("aria-expanded");
    expect(button).toBeDisabled();
  });

  it("shows a ticking elapsed duration while running, using startedAt", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-26T00:00:05Z"));
    flagState.deepTutorUiEnabled = true;
    const node = toolNode(tool());
    render(<TurnActivity activity={activity({ runStatus: "running" })} thinkingBlocks={[]} traceNodes={[node]} startedAt="2026-08-26T00:00:00Z" />);
    expect(document.querySelector(".turn-activity__duration")).toBeTruthy();
    vi.useRealTimers();
  });

  it("freezes the duration on the server-confirmed value once terminal", () => {
    flagState.deepTutorUiEnabled = true;
    const node = toolNode(tool());
    render(<TurnActivity activity={activity({ runStatus: "completed" })} thinkingBlocks={[]} traceNodes={[node]} durationMs={4500} startedAt="2026-08-26T00:00:00Z" />);
    expect(screen.getByText("4.5s")).toBeInTheDocument();
  });
});
