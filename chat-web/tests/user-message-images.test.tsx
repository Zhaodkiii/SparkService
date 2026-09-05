import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatMessages } from "@/components/chat/home/ChatMessages";
import { ChatRuntimeProvider } from "@/context/ChatRuntimeContext";
import type { ChatMessageWireDTO } from "@/types/sync";

const mocks = vi.hoisted(() => ({
  threads: {
    messages: [] as ChatMessageWireDTO[],
    error: null,
  },
}));

// runControl mock 需要运行时构造 state，工厂内惰性 import 避免 hoisting 顺序问题。
vi.mock("@/context/RunControlContext", async () => {
  const { createInitialChatRuntimeState } = await import("@/lib/event-reducer");
  return {
    useOptionalRunControl: () => ({
      run: null,
      state: createInitialChatRuntimeState(),
      busy: false,
      error: null,
      supportsImageInput: true,
    }),
  };
});

vi.mock("@/context/ThreadContext", () => ({
  useOptionalThreads: () => mocks.threads,
}));

function userMessage(blocks: ChatMessageWireDTO["blocks"]): ChatMessageWireDTO {
  return {
    thread_id: "thread-1",
    role: "user",
    client_message_id: "msg-1",
    delivery_state: "sent",
    created_at: "2026-09-04T01:30:00Z",
    blocks,
  };
}

function renderMessages(message: ChatMessageWireDTO) {
  mocks.threads.messages = [message];
  return render(<ChatRuntimeProvider initialScenario="history"><ChatMessages /></ChatRuntimeProvider>);
}

describe("用户消息图片渲染（CHAT-WEB-029）", () => {
  it("含 imageGallery block 的用户消息渲染图片容器而非丢弃", () => {
    const { container } = renderMessages(userMessage([
      { id: "b1", kind: "text", status: "ready", revision: 1, order_key: 1000, node_role: "timeline", payload: { text: { _0: "看看这张图片" } } },
      {
        id: "b2", kind: "imageGallery", status: "ready", revision: 1, order_key: 1100, node_role: "timeline",
        payload: { image_gallery: { _0: { images: [{ file_id: "file-1", url: "https://oss.example/a.webp", filename: "a.webp", order: 0 }] } } },
      },
    ]));
    expect(container.querySelector(".block--gallery")).not.toBeNull();
    expect(screen.getByRole("img", { name: "a.webp" })).toHaveAttribute("src", "https://oss.example/a.webp");
    // 文本气泡仍保留
    expect(screen.getByText("看看这张图片")).toBeInTheDocument();
  });

  it("图片-only 消息不渲染空文本气泡", () => {
    const { container } = renderMessages(userMessage([
      {
        id: "b1", kind: "imageGallery", status: "ready", revision: 1, order_key: 1100, node_role: "timeline",
        payload: { image_gallery: { _0: { images: [{ url: "https://oss.example/a.webp", filename: "a.webp" }] } } },
      },
    ]));
    expect(container.querySelector(".block--gallery")).not.toBeNull();
    expect(container.querySelector(".message__body")).toBeNull();
  });
});
