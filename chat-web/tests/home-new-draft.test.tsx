import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ThreadPullData, ThreadPushData } from "@/types/sync";
import { ThreadProvider, useOptionalThreads } from "@/context/ThreadContext";

const mocks = vi.hoisted(() => ({
  auth: { status: "authenticated", client: {} } as const,
  routerPush: vi.fn(),
  routerReplace: vi.fn(),
  pullThreads: vi.fn(),
  pushThreads: vi.fn(),
  pullMessages: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.routerPush, replace: mocks.routerReplace, prefetch: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/context/AuthContext", () => ({
  useOptionalAuth: () => mocks.auth,
}));

vi.mock("@/lib/api/chat-sync-api", () => ({
  SparkChatSyncApi: class {
    pullThreads(cursor?: string, limit?: number) { return mocks.pullThreads(cursor, limit); }
    pushThreads(threads: unknown[]) { return mocks.pushThreads(threads); }
    pullMessages(...args: unknown[]) { return mocks.pullMessages(...args); }
    deleteThreads() { return Promise.resolve(); }
  },
}));

const thread = {
  thread_id: "thread-history", title: "历史会话", scenario: "chat", is_deleted: false, updated_at: "2026-08-25T00:00:00Z", server_updated_at: "2026-08-25T00:00:00Z",
};

function Harness() {
  const threads = useOptionalThreads();
  return <div>
    <span data-testid="selected">{threads?.selectedThreadId ?? "null"}</span>
    <span data-testid="draft">{threads?.draft?.status ?? "null"}</span>
    <button onClick={() => threads?.startNewDraft()}>start</button>
    <button onClick={() => void threads?.materializeDraftThread()}>materialize</button>
  </div>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.pullMessages.mockResolvedValue({ messages: [], cursor: null, has_more: false });
  mocks.pushThreads.mockImplementation((threads: unknown[]) => Promise.resolve({ threads } as ThreadPushData));
});

describe("023 homepage new draft", () => {
  it("does not auto-select the most recent thread on /home load", async () => {
    mocks.pullThreads.mockResolvedValue({ threads: [thread], cursor: null, has_more: false } as ThreadPullData);
    render(<ThreadProvider><Harness /></ThreadProvider>);
    await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent("null"));
    // 历史 Thread 已进入侧栏列表，但选择态保持空（新 Draft），未回退到最近 Thread。
    await waitFor(() => expect(mocks.pullThreads).toHaveBeenCalledTimes(1));
  });

  it("startNewDraft clears the selection and creates a draft state", async () => {
    mocks.pullThreads.mockResolvedValue({ threads: [thread], cursor: null, has_more: false } as ThreadPullData);
    render(<ThreadProvider><Harness /></ThreadProvider>);
    await userEvent.click(screen.getByRole("button", { name: "start" }));
    expect(screen.getByTestId("selected")).toHaveTextContent("null");
    expect(screen.getByTestId("draft")).toHaveTextContent("draft");
  });

  it("materializeDraftThread creates a thread and sets the selection", async () => {
    mocks.pullThreads.mockResolvedValue({ threads: [], cursor: null, has_more: false } as ThreadPullData);
    render(<ThreadProvider><Harness /></ThreadProvider>);
    await userEvent.click(screen.getByRole("button", { name: "materialize" }));
    await waitFor(() => expect(screen.getByTestId("draft")).toHaveTextContent("materialized"));
    expect(mocks.pushThreads).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("selected")).not.toHaveTextContent("null");
    expect(mocks.routerPush).toHaveBeenCalled();
  });
});