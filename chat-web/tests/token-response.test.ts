import { describe, expect, it } from "vitest";
import { refreshTokenDataFromUpstream } from "@/lib/server/token-response";
import { refreshCookieOptions } from "@/lib/server/auth-cookies";

describe("refresh token response adapter", () => {
  it("accepts the existing flat Django refresh response", () => {
    expect(refreshTokenDataFromUpstream({ user_id: 1, access_token: "access", refresh_token: "refresh" })).toMatchObject({ access_token: "access", refresh_token: "refresh" });
  });

  it("accepts the canonical Spark envelope", () => {
    expect(refreshTokenDataFromUpstream({ code: 0, msg: "ok", data: { access_token: "access" } })).toMatchObject({ access_token: "access" });
  });

  it("rejects malformed successful responses", () => {
    expect(refreshTokenDataFromUpstream({ code: 0, data: {} })).toBeNull();
  });

  it("keeps the browser refresh cookie for thirty days", () => {
    expect(refreshCookieOptions().maxAge).toBe(60 * 60 * 24 * 30);
  });
});
