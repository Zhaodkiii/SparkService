import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TurnTraceRow } from "@/components/chat/turn/TurnTraceRow";
import type { ToolActivityDTO } from "@/types/tool";

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
    name: "get_health_resource_context",
    version: "v1",
    display_name: "读取健康资料",
    target: "server",
    status: "completed",
    round_index: 0,
    call_index: 0,
    revision: 3,
    display_args: { sections: ["过敏史", "慢性病"] },
    result_preview: "已读取 2 个健康档案分区",
    source_refs: [{ source_id: "member_profile:42", type: "member_profile" }],
    error: null,
    duplicate_of: null,
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

afterEach(() => {
  flagState.deepTutorUiEnabled = false;
});

describe("TurnTraceRow — legacy renderer (flag off)", () => {
  it("renders one joined summary line, not a separate verb/chip", () => {
    render(<ul><TurnTraceRow activity={tool()} /></ul>);
    expect(screen.getByText("读取健康资料")).toBeInTheDocument();
    expect(screen.getByText("已读取 2 个健康档案分区")).toBeInTheDocument();
    expect(document.querySelector(".turn-trace__chip")).toBeFalsy();
  });
});

describe("TurnTraceRow — DeepTutor renderer (flag on)", () => {
  it("separates verb, artifact chip and result line", () => {
    flagState.deepTutorUiEnabled = true;
    render(<ul><TurnTraceRow activity={tool()} /></ul>);
    expect(screen.getByText("读取健康资料")).toBeInTheDocument();
    expect(screen.getByText("过敏史、慢性病")).toBeInTheDocument();
    expect(screen.getByText("已读取 2 个健康档案分区")).toBeInTheDocument();
  });

  it("wraps a terminal row with extra detail in a native <details> disclosure", () => {
    flagState.deepTutorUiEnabled = true;
    render(<ul><TurnTraceRow activity={tool()} /></ul>);
    const details = document.querySelector("details.turn-trace__details");
    expect(details).toBeTruthy();
    expect(details?.querySelector(".turn-trace__details-body")?.textContent).toBe("已读取 2 个健康档案分区 · 引用 1 条资料");
  });

  it("does not render a disclosure for a still-running call (nothing to expand into)", () => {
    flagState.deepTutorUiEnabled = true;
    render(<ul><TurnTraceRow activity={tool({ status: "running", revision: 2, result_preview: null, source_refs: [] })} /></ul>);
    expect(document.querySelector("details.turn-trace__details")).toBeFalsy();
    expect(screen.getByText("执行中")).toBeInTheDocument();
  });
});
