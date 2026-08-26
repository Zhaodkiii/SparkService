import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatRuntimeProvider } from "@/context/ChatRuntimeContext";
import { ChatWorkspace } from "@/components/chat/home/ChatWorkspace";
import { AppShell } from "@/components/layout/AppShell";

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
});
