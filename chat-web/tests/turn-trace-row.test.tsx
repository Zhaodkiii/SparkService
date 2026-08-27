import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TurnTraceRow } from "@/components/chat/turn/TurnTraceRow";
import type { ToolActivityDTO } from "@/types/tool";

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

describe("TurnTraceRow", () => {
  it("separates verb, artifact chip and result line", () => {
    render(<ul><TurnTraceRow activity={tool()} /></ul>);
    expect(screen.getByText("读取健康资料")).toBeInTheDocument();
    expect(screen.getByText("过敏史、慢性病")).toBeInTheDocument();
    expect(screen.getByText("已读取 2 个健康档案分区")).toBeInTheDocument();
  });

  it("wraps a terminal row with extra detail in a native <details> disclosure", () => {
    render(<ul><TurnTraceRow activity={tool()} /></ul>);
    const details = document.querySelector("details.turn-trace__details");
    expect(details).toBeTruthy();
    expect(details?.querySelector(".turn-trace__details-body")?.textContent).toBe("已读取 2 个健康档案分区 · 引用 1 条资料");
  });

  it("does not render a disclosure for a still-running call", () => {
    render(<ul><TurnTraceRow activity={tool({ status: "running", revision: 2, result_preview: null, source_refs: [] })} /></ul>);
    expect(document.querySelector("details.turn-trace__details")).toBeFalsy();
    expect(screen.getByText("执行中")).toBeInTheDocument();
  });
});
