import { describe, expect, it } from "vitest";
import { normalizeSyncBlock, SparkChatSyncApi } from "@/lib/api/chat-sync-api";
import { SparkHttpClient } from "@/lib/api/http-client";
import { SparkRunApi } from "@/lib/api/run-api";
import { SparkContextApi } from "@/lib/api/context-api";

function clientWithRecorder() {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const http = new SparkHttpClient({
    baseUrl: "https://spark.test",
    fetcher: async (input, init) => {
      calls.push({ url: String(input), init });
      return new Response(JSON.stringify({ code: 0, msg: "ok", data: { run: null, events: [], next_after_sequence: 0, has_more: false } }), { status: 200 });
    },
  });
  return { http, calls };
}

describe("Spark P1 wire adapters", () => {
  it("calls fetch as a detached function for browser native fetch compatibility", async () => {
    const nativeLikeFetch = function (this: unknown) {
      if (this !== undefined) throw new TypeError("Illegal invocation");
      return Promise.resolve(new Response(JSON.stringify({ code: 0, msg: "ok", data: {} }), { status: 200 }));
    } as typeof fetch;
    const result = await new SparkHttpClient({ fetcher: nativeLikeFetch }).request<Record<string, never>>("GET", "/api/test");
    expect(result.ok).toBe(true);
  });

  it("keeps the iOS tagged sync Block shape and rejects the old flat role", () => {
    expect(normalizeSyncBlock({ id: "block-1", kind: "text", status: "ready", revision: 2, order_key: 1000, node_role: "timeline", payload: { text: { _0: "server text" } } })).toMatchObject({
      id: "block-1",
      revision: 2,
      kind: "text",
      node_role: "timeline",
      payload: { text: { _0: "server text" } },
    });
    expect(normalizeSyncBlock({ id: "bad", kind: "text", node_role: "content", payload: { text: "server text" } }).kind).toBe("");
  });
  it("keeps Thread Sync cursor and payload semantics", async () => {
    const { http, calls } = clientWithRecorder();
    const api = new SparkChatSyncApi(http);
    await api.pullThreads("cursor/one", 50);
    await api.deleteThreads(["thread-1"]);
    expect(calls[0].url).toBe("https://spark.test/api/v1/ai/chat/sync/thread-pull/?cursor=cursor%2Fone&limit=50");
    expect(JSON.parse(String(calls[1].init?.body))).toEqual({ thread_ids: ["thread-1"] });
  });

  it("sends Run idempotency key and encoded thread/run paths", async () => {
    const { http, calls } = clientWithRecorder();
    const api = new SparkRunApi(http);
    await api.create("thread/one", { input_message: { thread_id: "thread/one", role: "user", client_message_id: "msg-1", blocks: [{ kind: "text", node_role: "timeline", payload: { text: { _0: "hi" } } }] }, run_options: { capability: "chat", context_inputs: [], attachments: [], client: { platform: "web", version: "0.1.0", device_id: "device-1" } } }, "intent-1");
    await api.events("run/one", 4, 20);
    await api.createWebSocketTicket();
    expect(calls[0].url).toContain("/threads/thread%2Fone/runs/");
    expect(new Headers(calls[0].init?.headers).get("Idempotency-Key")).toBe("intent-1");
    expect(calls[1].url).toContain("/runs/run%2Fone/events/?after_sequence=4&limit=20");
    expect(calls[2].url).toBe("https://spark.test/api/v1/ai/chat/ws-tickets/");
    expect(calls[2].init?.method).toBe("POST");
  });

  it("uses optimistic concurrency for Preferences and exposes the safe Context summary", async () => {
    const { http, calls } = clientWithRecorder();
    const api = new SparkContextApi(http);
    await api.updatePreferences("thread/one", 7, { language: "zh-CN" });
    await api.getSummary("run/one");
    expect(new Headers(calls[0].init?.headers).get("If-Match")).toBe('"7"');
    expect(JSON.parse(String(calls[0].init?.body))).toMatchObject({ revision: 7, language: "zh-CN" });
    expect(calls[1].url).toContain("/runs/run%2Fone/context-summary/");
  });
});
