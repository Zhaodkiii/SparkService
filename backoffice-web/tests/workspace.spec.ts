import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { defineComponent } from "vue";
import { mount, type VueWrapper } from "@vue/test-utils";
import { useCustomizationWorkspace } from "../src/features/customizations/useCustomizationWorkspace";
import type { Detail } from "../src/features/customizations/types";
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../src/api/http", () => ({
  default: mocks,
  ApiError: class ApiError extends Error {
    status?: number;
    constructor(m: string, s?: number) {
      super(m);
      this.status = s;
    }
  },
}));
vi.mock("../src/stores/auth", () => ({
  useAuthStore: () => ({ user: { id: 7 } }),
}));
vi.mock("ant-design-vue", () => ({
  Modal: { confirm: (options: { onOk: () => void }) => options.onOk() },
}));
function detail(id: string, revision = 1): Detail {
  return {
    id,
    title: id,
    status: "in_production",
    revision,
    due_at: null,
    internal_note: id + " server note",
    submissions: [],
    accepted_submission_id: 1,
    latest_submission_id: 1,
    allowed_actions: ["production"],
    jobs: [],
    assets: [],
    deliveries: [],
    events: [],
    notifications: [],
    audit: [],
  } as unknown as Detail;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}
let wrapper: VueWrapper, w: ReturnType<typeof useCustomizationWorkspace>;
function setup() {
  wrapper = mount(
    defineComponent({
      setup() {
        w = useCustomizationWorkspace();
        return () => null;
      },
    }),
  );
}
beforeEach(() => {
  sessionStorage.clear();
  mocks.get.mockReset();
  mocks.post.mockReset();
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith("operators/")) return { results: [] };
    if (path.includes("requests/?"))
      return { results: [], summary: {}, next_page: null };
    if (path.includes("/operations/")) return { applied: false };
    return detail(path.includes("/A/") ? "A" : "B");
  });
});
afterEach(() => {
  wrapper?.unmount();
  vi.useRealTimers();
});
describe("workspace request and edit lifecycle", () => {
  it("late detail A cannot overwrite opened request B", async () => {
    setup();
    const old = deferred<Detail>();
    mocks.get.mockImplementation(async (path: string) =>
      path.includes("/A/")
        ? old.promise
        : path.includes("/B/")
          ? detail("B")
          : { results: [], summary: {} },
    );
    const first = w.open("A");
    await Promise.resolve();
    await w.open("B");
    old.resolve(detail("A"));
    await first;
    expect(w.current.value?.id).toBe("B");
    expect(w.editor.value.internalNote).toBe("B server note");
  });
  it("switching requests clears file, upload progress, instructions and candidate reviews", async () => {
    setup();
    await w.open("A");
    w.editor.value.internalNote = "A draft";
    w.editor.value.reviews.c = {
      used: ["photo-A"],
      reviewed: true,
      message: "A instructions",
    };
    w.archive.value = new File(["a"], "A.zip");
    w.uploadProgress.value = 0.7;
    await w.open("B");
    expect(w.archive.value).toBeUndefined();
    expect(w.uploadProgress.value).toBe(0);
    expect(w.editor.value.reviews).toEqual({});
    expect(w.editor.value.internalNote).toBe("B server note");
  });
  it("refresh preserves unsaved local notes and date while updating server revision", async () => {
    setup();
    await w.open("A");
    w.editor.value.internalNote = "local unsaved";
    w.editor.value.due = "2026-11-01T00:00:00Z";
    mocks.get.mockResolvedValue({
      ...detail("A", 2),
      internal_note: "other admin",
    });
    await w.refresh();
    expect(w.current.value?.revision).toBe(2);
    expect(w.editor.value.internalNote).toBe("local unsaved");
    expect(w.editor.value.due).toBe("2026-11-01T00:00:00Z");
  });
  it("a stale refresh cannot roll back a successful action response", async () => {
    setup();
    await w.open("A");
    const old = deferred<Detail>();
    mocks.get.mockReturnValueOnce(old.promise);
    const refresh = w.refresh();
    mocks.post.mockResolvedValue(detail("A", 3));
    await w.act("production", { due_at: null, internal_note: "saved" });
    old.resolve(detail("A", 2));
    await refresh;
    expect(w.current.value?.revision).toBe(3);
  });
  it("closing while polling stops requests and cannot reopen the drawer", async () => {
    vi.useFakeTimers();
    setup();
    mocks.get.mockResolvedValue({
      ...detail("A"),
      jobs: [{ id: "j", kind: "delivery", status: "processing" }],
    });
    await w.open("A");
    await w.close();
    const count = mocks.get.mock.calls.length;
    await vi.advanceTimersByTimeAsync(10000);
    expect(w.current.value).toBeNull();
    expect(mocks.get.mock.calls.length).toBe(count);
  });
  it("an action completing after a switch cannot write into the new request", async () => {
    setup();
    await w.open("A");
    const action = deferred<Detail>();
    mocks.post.mockReturnValue(action.promise);
    const pending = w.act("production", { internal_note: "A" });
    await new Promise((r) => setTimeout(r, 15));
    await w.open("B");
    action.resolve(detail("A", 2));
    await pending;
    expect(w.current.value?.id).toBe("B");
    expect(w.editor.value.internalNote).toBe("B server note");
  });
  it("network retry reuses original body and idempotency key", async () => {
    setup();
    await w.open("A");
    mocks.post.mockRejectedValueOnce(new Error("Network Error"));
    await w.act("production", { internal_note: "A local", due_at: null });
    expect(w.pending.value).not.toBeNull();
    const first = mocks.post.mock.calls[0];
    mocks.post.mockResolvedValue(detail("A", 2));
    await w.retryAction();
    const second = mocks.post.mock.calls[1];
    expect(second?.[1]).toEqual(first?.[1]);
    expect(second?.[2]).toEqual(first?.[2]);
    expect(w.pending.value).toBeNull();
  });
  it("conflict refresh keeps local draft and shows updated server values for comparison", async () => {
    setup();
    await w.open("A");
    w.editor.value.internalNote = "local";
    const { ApiError } = await import("../src/api/http");
    mocks.post.mockRejectedValue(new ApiError("内容已更新", 409));
    mocks.get.mockResolvedValue({
      ...detail("A", 2),
      internal_note: "server changed",
    });
    await w.act("production", { internal_note: "local", due_at: null });
    expect(w.conflict.value).toBe(true);
    expect(w.editor.value.internalNote).toBe("local");
    expect(w.current.value?.internal_note).toBe("server changed");
    expect(w.pending.value).toBeNull();
  });
});
