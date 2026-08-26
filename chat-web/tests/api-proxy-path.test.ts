import { afterEach, describe, expect, it, vi } from "vitest";
import { callSparkUpstream, sparkApiPathFromRequest } from "@/lib/server/upstream";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Spark API BFF path forwarding", () => {
  it("preserves the canonical trailing slash and query string", () => {
    const request = new Request(
      "http://localhost:9001/api/v1/ai/chat/threads/thread-1/runs/?after_sequence=4&limit=20",
    );

    expect(sparkApiPathFromRequest(request)).toBe(
      "/api/v1/ai/chat/threads/thread-1/runs/?after_sequence=4&limit=20",
    );
  });

  it("rejects paths outside the Spark API proxy namespace", () => {
    expect(() => sparkApiPathFromRequest(new Request("http://localhost:9001/auth/session/"))).toThrow(
      "Unsupported Spark API proxy path",
    );
  });

  it("does not follow an upstream redirect that could rewrite POST to GET", async () => {
    let receivedInit: RequestInit | undefined;
    const fetcher = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      receivedInit = init;
      return new Response(null, { status: 301, headers: { location: "/api/v1/ai/chat/threads/thread-1/runs/" } });
    });
    vi.stubGlobal("fetch", fetcher);

    const result = await callSparkUpstream(
      "/api/v1/ai/chat/threads/thread-1/runs/",
      { method: "POST", body: "{}" },
      "request-1",
    );

    expect(result.response.status).toBe(301);
    expect(fetcher).toHaveBeenCalledOnce();
    expect(receivedInit).toMatchObject({ method: "POST", redirect: "manual" });
  });
});
