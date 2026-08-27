import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { cookieSet } = vi.hoisted(() => ({ cookieSet: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => undefined, set: cookieSet }) }));

import { POST as appleCallbackPost } from "@/app/api/auth/apple/callback/route";
import { publicWebOrigin } from "@/lib/server/public-origin";

function formRequest(url: string, body: URLSearchParams): Request {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
}

describe("publicWebOrigin", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("prefers SPARK_PUBLIC_WEB_BASE_URL over the internal listening address", () => {
    vi.stubEnv("SPARK_PUBLIC_WEB_BASE_URL", "https://chat.dreamwhale.top");
    expect(publicWebOrigin({ url: "https://0.0.0.0:9001/api/auth/apple/callback" })).toBe("https://chat.dreamwhale.top");
  });

  it("falls back to request origin when the env var is absent", () => {
    vi.stubEnv("SPARK_PUBLIC_WEB_BASE_URL", "");
    expect(publicWebOrigin({ url: "https://chat.dreamwhale.top/api/auth/apple/callback" })).toBe("https://chat.dreamwhale.top");
  });
});

describe("apple callback redirect origin (CHAT-WEB-019E)", () => {
  beforeEach(() => {
    cookieSet.mockClear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("redirects to the public origin even when the proxied request URL is the internal listen address", async () => {
    vi.stubEnv("SPARK_PUBLIC_WEB_BASE_URL", "https://chat.dreamwhale.top");
    const body = new URLSearchParams({ state: "bad", id_token: "bad" });
    const response = await appleCallbackPost(formRequest("https://0.0.0.0:9001/api/auth/apple/callback", body));

    expect(response.headers.get("location")).toMatch(/^https:\/\/chat\.dreamwhale\.top\/login\?error=/);
    expect(response.headers.get("location")).not.toContain("0.0.0.0");
  });
});