import { callSparkUpstream, failureEnvelope, isRecord, jsonEnvelope, requestIdFrom, stringField, upstreamResponse } from "@/lib/server/upstream";
import { authDiagnosticLog, deviceLogSuffix, maskPhone } from "@/lib/auth/diagnostics";

export async function POST(request: Request) {
  const requestId = requestIdFrom(request);
  let raw: unknown;
  try { raw = await request.json(); } catch { return failureEnvelope(400, "请求格式错误", requestId); }
  if (!isRecord(raw)) return failureEnvelope(400, "请求格式错误", requestId);
  const phone = stringField(raw.phone_number ?? raw.phone, 32);
  if (!phone) {
    authDiagnosticLog("warn", "bff", "phone_otp.request.validation_failed", { request_id: requestId });
    return failureEnvelope(400, "手机号格式错误", requestId);
  }
  const startedAt = Date.now();
  const deviceId = stringField(raw.device_id, 128) || `web-${requestId}`;
  authDiagnosticLog("info", "bff", "phone_otp.request.upstream_started", { request_id: requestId, phone: maskPhone(phone), device: deviceLogSuffix(deviceId) });
  let result: Awaited<ReturnType<typeof callSparkUpstream>>;
  try {
    result = await callSparkUpstream("/api/v1/otp/phone/request/", { method: "POST", body: JSON.stringify({ phone_number: phone, bundle_id: process.env.SPARK_WEB_SERVICE_ID || "cn.Zhaodk.Health.web", device_id: deviceId, scene: stringField(raw.scene, 64) || "login" }) }, requestId);
  } catch (cause) {
    authDiagnosticLog("error", "bff", "phone_otp.request.upstream_unreachable", { request_id: requestId, duration_ms: Date.now() - startedAt, error_type: cause instanceof Error ? cause.name : typeof cause });
    return failureEnvelope(503, "本地服务连接失败", requestId);
  }
  const businessCode = isRecord(result.body) && typeof result.body.code === "number" ? result.body.code : null;
  authDiagnosticLog(result.response.ok ? "info" : "warn", "bff", result.response.ok ? "phone_otp.request.upstream_succeeded" : "phone_otp.request.upstream_failed", { request_id: requestId, duration_ms: Date.now() - startedAt, http_status: result.response.status, business_code: businessCode });
  if (!result.response.ok) return upstreamResponse(result);
  if (!isRecord(result.body)) return failureEnvelope(502, "上游响应格式错误", requestId);
  return jsonEnvelope(result.body, result.response.status, requestId);
}
