import { describe, expect, it } from "vitest";
import { SparkApiError } from "@/lib/api/http-client";
import { normalizeMainlandPhone, phoneOtpErrorMessage } from "@/lib/auth/phone";
import { deviceLogSuffix, maskPhone } from "@/lib/auth/diagnostics";

describe("phone login adapter", () => {
  it("normalizes local and +86 mainland mobile numbers", () => {
    expect(normalizeMainlandPhone("138 0013 8000")).toBe("+8613800138000");
    expect(normalizeMainlandPhone("+86 138-0013-8000")).toBe("+8613800138000");
    expect(normalizeMainlandPhone("123456")).toBeNull();
  });

  it("exposes actionable upstream failures instead of hiding them", () => {
    const error = new SparkApiError({ ok: false, httpStatus: 429, code: 42901, messageKey: "auth.otp.rate_limited", retryable: true });
    expect(phoneOtpErrorMessage(error, "request")).toBe("发送过于频繁，请稍后再试");
    expect(phoneOtpErrorMessage(new TypeError("fetch failed"), "request")).toContain("本地服务");
  });

  it("redacts identifiers used by diagnostic logs", () => {
    expect(maskPhone("+8613800138000")).toBe("86***8000");
    expect(deviceLogSuffix("web-12345678-abcdefgh")).toBe("***abcdefgh");
    expect(maskPhone("123")).toBe("***");
  });
});
