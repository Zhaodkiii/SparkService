import { cookies } from "next/headers";
import { REFRESH_COOKIE, refreshCookieOptions } from "@/lib/server/auth-cookies";
import { callSparkUpstream, failureEnvelope, isRecord, jsonEnvelope, requestIdFrom, stringField } from "@/lib/server/upstream";
import { authDiagnosticLog, deviceLogSuffix, maskPhone } from "@/lib/auth/diagnostics";

function publicTokenEnvelope(body: Record<string, unknown>) {
  const data = isRecord(body.data) ? body.data : null;
  if (!data || typeof data.access_token !== "string" || typeof data.refresh_token !== "string") return null;
  const { refresh_token: _refresh, ...publicData } = data;
  return { ...body, data: publicData };
}

export async function POST(request: Request) {
  const requestId = requestIdFrom(request);
  let raw: unknown;
  try { raw = await request.json(); } catch { return failureEnvelope(400, "请求格式错误", requestId); }
  if (!isRecord(raw)) return failureEnvelope(400, "请求格式错误", requestId);
  const otpId = stringField(raw.otp_id, 128);
  const code = stringField(raw.code, 16);
  const phone = stringField(raw.phone_number ?? raw.phone, 32);
  if (!otpId || !code || !phone) {
    authDiagnosticLog("warn", "bff", "phone_otp.verify.validation_failed", { request_id: requestId, has_otp_id: Boolean(otpId), has_code: Boolean(code), has_phone: Boolean(phone) });
    return failureEnvelope(400, "验证码信息不完整", requestId);
  }
  const startedAt = Date.now();
  const deviceId = stringField(raw.device_id, 128) || `web-${requestId}`;
  authDiagnosticLog("info", "bff", "phone_otp.verify.upstream_started", { request_id: requestId, phone: maskPhone(phone), device: deviceLogSuffix(deviceId) });
  let result: Awaited<ReturnType<typeof callSparkUpstream>>;
  try {
    result = await callSparkUpstream("/api/v1/otp/phone/verify/", { method: "POST", body: JSON.stringify({ otp_id: otpId, phone_number: phone, code, bundle_id: process.env.SPARK_WEB_SERVICE_ID || "cn.Zhaodk.Health.web", device_id: deviceId }) }, requestId);
  } catch (cause) {
    authDiagnosticLog("error", "bff", "phone_otp.verify.upstream_unreachable", { request_id: requestId, duration_ms: Date.now() - startedAt, error_type: cause instanceof Error ? cause.name : typeof cause });
    return failureEnvelope(503, "本地服务连接失败", requestId);
  }
  const businessCode = isRecord(result.body) && typeof result.body.code === "number" ? result.body.code : null;
  authDiagnosticLog(result.response.ok ? "info" : "warn", "bff", result.response.ok ? "phone_otp.verify.upstream_succeeded" : "phone_otp.verify.upstream_failed", { request_id: requestId, duration_ms: Date.now() - startedAt, http_status: result.response.status, business_code: businessCode });
  if (!result.response.ok) return jsonEnvelope(result.body, result.response.status, requestId);
  if (!isRecord(result.body)) return failureEnvelope(502, "上游响应格式错误", requestId);
  const safe = publicTokenEnvelope(result.body);
  const data = isRecord(result.body.data) ? result.body.data : null;
  if (!safe || !data) return failureEnvelope(502, "登录响应缺少令牌", requestId);
  const store = await cookies();
  store.set(REFRESH_COOKIE, String(data.refresh_token), refreshCookieOptions());
  return jsonEnvelope(safe, result.response.status, requestId);
}
