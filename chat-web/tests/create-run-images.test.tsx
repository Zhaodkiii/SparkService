import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RunControlProvider, useRunControl } from "@/context/RunControlContext";
import type { CreateRunRequestDTO } from "@/types/run";
import type { ReadyImagePayload } from "@/lib/chat/image-drafts";

const mocks = vi.hoisted(() => ({
  // auth 必须是稳定引用：RunControlProvider 以其为依赖构造 api，每渲染新建会导致效应死循环。
  auth: { status: "authenticated", client: {} } as const,
  threads: {
    selectedThreadId: "thread-1",
    appendOptimisticMessage: vi.fn(),
    updateMessageDelivery: vi.fn(),
    reloadMessages: vi.fn(async () => {}),
  },
  create: vi.fn(),
  readiness: vi.fn(),
  getActive: vi.fn(),
  events: vi.fn(),
}));

vi.mock("@/context/AuthContext", () => ({
  useOptionalAuth: () => mocks.auth,
}));

vi.mock("@/context/ThreadContext", () => ({
  useOptionalThreads: () => mocks.threads,
}));

vi.mock("@/lib/api/run-api", () => ({
  SparkRunApi: class {
    create(...args: unknown[]) { return mocks.create(...args); }
    readiness() { return mocks.readiness(); }
    getActive() { return mocks.getActive(); }
    events(...args: unknown[]) { return mocks.events(...args); }
    get() { return Promise.resolve({ run: null }); }
    cancel() { return Promise.resolve({ run: null }); }
    regenerate() { return Promise.reject(new Error("not implemented")); }
    createWebSocketTicket() { return Promise.reject(new Error("not implemented")); }
  },
}));

vi.mock("@/lib/api/interaction-api", () => ({
  SparkInteractionApi: class {},
}));

const image: ReadyImagePayload = {
  fileId: "file-1",
  fileUuid: "7e4b4c1f-8f5c-4b0c-9f3e-2f6a9b0c1d2e",
  displayUrl: "https://oss.example/a.webp",
  fileName: "a.webp",
  mimeType: "image/webp",
  fileSize: 1024,
  order: 0,
};

function Harness() {
  const runControl = useRunControl();
  return <div>
    <span data-testid="capability">{String(runControl.supportsImageInput)}</span>
    <button onClick={() => void runControl.createRun("看下这张", null, "thread-1", { images: [image], clientMessageId: "msg-fixed-1" })}>send-with-text</button>
    <button onClick={() => void runControl.createRun("", null, "thread-1", { images: [image], clientMessageId: "msg-fixed-1" })}>send-image-only</button>
    <button onClick={() => void runControl.createRun("", null, "thread-1")}>send-empty</button>
    <button onClick={() => void runControl.createRun("重试", null, "thread-1", { images: [image], clientMessageId: "msg-fixed-1" })}>send-retry</button>
  </div>;
}

function lastPayload(): CreateRunRequestDTO {
  return mocks.create.mock.calls[mocks.create.mock.calls.length - 1][1] as CreateRunRequestDTO;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getActive.mockResolvedValue({ run: null });
  mocks.events.mockResolvedValue({ events: [], next_after_sequence: 0, has_more: false });
  mocks.create.mockResolvedValue({
    run: { id: "run-1", thread_id: "thread-1", status: "queued", capability: "chat", last_sequence: 0 },
    subscription: { websocket_path: "/ws", resume_after_sequence: 0 },
  });
  mocks.readiness.mockResolvedValue({
    available: true, code: "ok", retryable: false, checked_at: null, executor: "local",
    model_binding_configured: true, worker_healthy: true, config_version: "v1", supports_image_input: true,
  });
});

describe("createRun 图片载荷（CHAT-WEB-029）", () => {
  it("有图时 blocks 含 imageGallery 且 attachments 含图片元数据", async () => {
    render(<RunControlProvider><Harness /></RunControlProvider>);
    await userEvent.click(screen.getByRole("button", { name: "send-with-text" }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1));

    const payload = lastPayload();
    expect(payload.input_message.client_message_id).toBe("msg-fixed-1");
    expect(payload.input_message.blocks).toHaveLength(2);
    const [textBlock, galleryBlock] = payload.input_message.blocks;
    expect(textBlock.kind).toBe("text");
    expect(textBlock.payload).toEqual({ text: { _0: "看下这张" } });
    expect(galleryBlock.kind).toBe("imageGallery");
    // canonical tagged union，_0 与 iOS 一致直接是图片数组；id/type 为 iOS ChatAttachment 必填字段
    expect(galleryBlock.payload).toEqual({
      image_gallery: {
        _0: [{ id: "7e4b4c1f-8f5c-4b0c-9f3e-2f6a9b0c1d2e", type: "image", file_id: "file-1", url: "https://oss.example/a.webp", filename: "a.webp", mime_type: "image/webp", order: 0 }],
      },
    });
    expect(payload.run_options.attachments).toEqual([
      { id: "7e4b4c1f-8f5c-4b0c-9f3e-2f6a9b0c1d2e", file_id: "file-1", type: "image", order: 0, mime_type: "image/webp", file_size: 1024, display_url: "https://oss.example/a.webp" },
    ]);
    // 乐观消息与请求 blocks 一致，图片立即可见
    const optimistic = mocks.threads.appendOptimisticMessage.mock.calls[0][0];
    expect(optimistic.blocks).toHaveLength(2);
    expect(optimistic.blocks[1].kind).toBe("imageGallery");
  });

  it("图片-only：无 text block", async () => {
    render(<RunControlProvider><Harness /></RunControlProvider>);
    await userEvent.click(screen.getByRole("button", { name: "send-image-only" }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1));
    const payload = lastPayload();
    expect(payload.input_message.blocks).toHaveLength(1);
    expect(payload.input_message.blocks[0].kind).toBe("imageGallery");
  });

  it("文本与图片都为空时不创建 Run", async () => {
    render(<RunControlProvider><Harness /></RunControlProvider>);
    await userEvent.click(screen.getByRole("button", { name: "send-empty" }));
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it("重试复用同一 client_message_id，Idempotency-Key 每次新生成", async () => {
    render(<RunControlProvider><Harness /></RunControlProvider>);
    await userEvent.click(screen.getByRole("button", { name: "send-with-text" }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByRole("button", { name: "send-retry" }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(2));
    const first = mocks.create.mock.calls[0];
    const second = mocks.create.mock.calls[1];
    expect((first[1] as CreateRunRequestDTO).input_message.client_message_id).toBe("msg-fixed-1");
    expect((second[1] as CreateRunRequestDTO).input_message.client_message_id).toBe("msg-fixed-1");
    expect(first[2]).not.toBe(second[2]);
  });

  it("readiness 返回 supports_image_input 时能力为 true，异常时为 false", async () => {
    render(<RunControlProvider><Harness /></RunControlProvider>);
    await waitFor(() => expect(screen.getByTestId("capability")).toHaveTextContent("true"));
  });

  it("readiness 请求失败时能力按不支持处理", async () => {
    mocks.readiness.mockRejectedValue(new Error("network down"));
    render(<RunControlProvider><Harness /></RunControlProvider>);
    await waitFor(() => expect(mocks.readiness).toHaveBeenCalled());
    expect(screen.getByTestId("capability")).toHaveTextContent("false");
  });
});
