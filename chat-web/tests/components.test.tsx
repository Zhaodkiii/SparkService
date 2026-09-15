import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatRuntimeProvider } from "@/context/ChatRuntimeContext";
import { ChatWorkspace } from "@/components/chat/home/ChatWorkspace";
import { UserMessageContent } from "@/components/chat/home/UserMessageBubble";
import { AppShell } from "@/components/layout/AppShell";
import type { ChatBlockDTO } from "@/types/chat";

vi.mock("next/navigation", () => ({
  usePathname: () => "/home",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

describe("P0 static workspace", () => {
  it("renders an accessible chat composer and navigation", () => {
    render(<ChatRuntimeProvider initialScenario="history"><AppShell><ChatWorkspace /></AppShell></ChatRuntimeProvider>);
    expect(screen.getByRole("textbox", { name: "输入消息" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发送" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "全局导航" })).toBeInTheDocument();
  });

  it("renders a health resource reference card inside a user message", () => {
    const block: ChatBlockDTO = {
      id: "report-reference",
      kind: "healthResourceReference",
      status: "ready",
      revision: 1,
      order_key: 1,
      node_role: "timeline",
      payload: {
        health_resource_reference: {
          _0: { resource_type: "examination_report", resource_id: 327, member_id: 2, ref_index: 2 },
        },
      },
    };

    render(<UserMessageContent blocks={[block]} />);

    expect(screen.getByRole("button", { name: "检查报告：检查报告 #327" })).toBeInTheDocument();
    expect(screen.getByText("资料编号：327 · 成员 2")).toBeInTheDocument();
  });
});
