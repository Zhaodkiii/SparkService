import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatRuntimeProvider } from "@/context/ChatRuntimeContext";
import { ChatWorkspace } from "@/components/chat/home/ChatWorkspace";
import { AppShell } from "@/components/layout/AppShell";

describe("P0 static workspace", () => {
  it("renders an accessible chat composer and navigation", () => {
    render(<ChatRuntimeProvider initialScenario="history"><AppShell><ChatWorkspace /></AppShell></ChatRuntimeProvider>);
    expect(screen.getByRole("textbox", { name: "输入消息" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发送" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "全局导航" })).toBeInTheDocument();
  });
});
