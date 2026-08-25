import { describe, expect, it } from "vitest";
import { failureFromEnvelope, normalizeResponse } from "@/lib/api/normalize";
import { SparkApiError, SparkHttpClient } from "@/lib/api/http-client";

function response(status: number, requestId = "req-test"): Response {
  return new Response(null, { status, headers: { "x-request-id": requestId } });
}

describe("Spark API response normalization", () => {
  it("unwraps success envelope and keeps request id", () => {
    const result = normalizeResponse(response(202), { code: 0, msg: "accepted", data: { id: "run-1" } });
    expect(result).toEqual({ ok: true, httpStatus: 202, requestId: "req-test", data: { id: "run-1" } });
  });

  it("maps business errors without exposing the raw message as a UI key", () => {
    const result = failureFromEnvelope(response(409), { code: 40992, msg: "chat_idempotency_conflict", data: { request_id: "req-body", retryable: false } });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.messageKey).toBe("chat.idempotency_conflict");
    expect(result.requestId).toBe("req-test");
    expect(result.retryable).toBe(false);
  });

  it("rejects malformed and empty envelopes", () => {
    expect(normalizeResponse(response(200), { code: 0 })).toMatchObject({ ok: false, messageKey: "api.invalid_envelope" });
    expect(normalizeResponse(response(502), "upstream html")).toMatchObject({ ok: false, httpStatus: 502, retryable: true });
  });

  it("refreshes once on 401 and retries with the new access token", async () => {
    let calls = 0;
    let token = "expired";
    const client = new SparkHttpClient({
      getAccessToken: () => token,
      refreshAccessToken: async () => {
        token = "fresh";
        return token;
      },
      fetcher: async (_input, init) => {
        calls += 1;
        const auth = new Headers(init?.headers).get("Authorization");
        if (auth === "Bearer expired") return new Response(JSON.stringify({ code: 40102, msg: "token_not_valid", data: null }), { status: 401 });
        return new Response(JSON.stringify({ code: 0, msg: "ok", data: { value: 1 } }), { status: 200 });
      },
    });
    await expect(client.requestOrThrow("GET", "/api/test")).resolves.toEqual({ value: 1 });
    expect(calls).toBe(2);
  });

  it("does not refresh twice and exposes a typed error for callers that want exceptions", async () => {
    const client = new SparkHttpClient({ fetcher: async () => new Response(JSON.stringify({ code: 50392, msg: "chat_server_runs_disabled", data: { retryable: false } }), { status: 503 }) });
    await expect(client.requestOrThrow("POST", "/runs")).rejects.toSatisfy((error: unknown) => error instanceof SparkApiError && error.failure.messageKey === "chat.server_runs_disabled");
  });
});
