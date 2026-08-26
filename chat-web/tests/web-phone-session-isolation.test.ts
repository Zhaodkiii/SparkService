import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { cookieSet } = vi.hoisted(() => ({ cookieSet: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: async () => ({ set: cookieSet }) }));

import { POST as phoneRequestPost } from "@/app/api/auth/phone/request/route";
import { POST as phoneVerifyPost } from "@/app/api/auth/phone/verify/route";

function jsonRequest(url: string, body: unknown): Request {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

const upstreamBody = {
  code: 0,
  msg: "ok",
  data: {
    otp_id: "otp-1",
    expires_in: 300,
    user_id: 1,
    access_token: "access-token",
    refresh_token: "refresh-token",
    token_type: "Bearer",
  },
};

describe("web phone BFF isolation (CHAT-WEB-020D)", () => {
  const fetchCalls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];

  beforeEach(() => {
    cookieSet.mockClear();
    fetchCalls.length = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      fetchCalls.push({ input, init });
      return new Response(JSON.stringify(upstreamBody), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("request route calls only the web upstream and drops bundle/device", async () => {
    await phoneRequestPost(jsonRequest(
      "http://localhost:9001/api/auth/phone/request",
      { phone_number: "+8613800138000", bundle_id: "cn.Zhaodk.Health.web", device_id: "web-x", scene: "login" },
    ));

    expect(fetchCalls).toHaveLength(1);
    expect(new URL(String(fetchCalls[0].input)).pathname).toBe("/api/v1/auth/phone/web/otp/request/");

    const body = JSON.parse(String(fetchCalls[0].init?.body));
    expect(body).toEqual({ phone_number: "+8613800138000", scene: "login" });
    expect(body).not.toHaveProperty("bundle_id");
    expect(body).not.toHaveProperty("device_id");
  });

  it("verify route calls only the web upstream, sets the refresh cookie and hides refresh_token", async () => {
    const response = await phoneVerifyPost(jsonRequest(
      "http://localhost:9001/api/auth/phone/verify",
      { otp_id: "otp-1", phone_number: "+8613800138000", code: "123456", bundle_id: "cn.Zhaodk.Health.web", device_id: "web-x" },
    ));

    expect(fetchCalls).toHaveLength(1);
    expect(new URL(String(fetchCalls[0].input)).pathname).toBe("/api/v1/auth/phone/web/otp/verify/");

    const body = JSON.parse(String(fetchCalls[0].init?.body));
    expect(body).toEqual({ otp_id: "otp-1", phone_number: "+8613800138000", code: "123456" });
    expect(body).not.toHaveProperty("bundle_id");
    expect(body).not.toHaveProperty("device_id");

    expect(cookieSet).toHaveBeenCalledOnce();
    expect(cookieSet.mock.calls[0][1]).toBe("refresh-token");

    const json = await response.json();
    expect(json.data).not.toHaveProperty("refresh_token");
    expect(json.data.access_token).toBe("access-token");
  });

  it("does not fall back to a mobile endpoint when the web upstream fails", async () => {
    vi.unstubAllGlobals();
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      fetchCalls.push({ input: _input, init: _init });
      return new Response(JSON.stringify({ code: 50375, msg: "web_phone_login_disabled", data: null }), {
        status: 503,
        headers: { "content-type": "application/json" },
      });
    }));

    const response = await phoneRequestPost(jsonRequest(
      "http://localhost:9001/api/auth/phone/request",
      { phone_number: "+8613800138000", scene: "login" },
    ));

    expect(response.status).toBe(503);
    expect(fetchCalls).toHaveLength(1);
    expect(new URL(String(fetchCalls[0].input)).pathname).toBe("/api/v1/auth/phone/web/otp/request/");
  });
});