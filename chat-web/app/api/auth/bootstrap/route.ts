import { cookies } from "next/headers";
import { REFRESH_COOKIE, refreshCookieOptions } from "@/lib/server/auth-cookies";
import { callSparkUpstream, failureEnvelope, isRecord, jsonEnvelope, requestIdFrom, stringField } from "@/lib/server/upstream";
import { refreshTokenDataFromUpstream } from "@/lib/server/token-response";
import { authDiagnosticLog } from "@/lib/auth/diagnostics";

/**
 * Chat Web BFF 登录恢复入口（CHAT-WEB-019E）。
 *
 * 以 Web refresh Token 恢复 Session：请求体只携带 refresh_token，
 * 不再提交随机移动 device_id / bundle_id。服务端按 token 内的
 * web_session_id 分派到 AccountWebSession 域（与移动会话隔离）。
 * 注意：本入口不是 /api/v1/ai/config/bootstrap，AI 配置 bootstrap 完全不变。
 */
export async function POST(request: Request) {
  const requestId = requestIdFrom(request);
  const store = await cookies();
  const refresh = store.get(REFRESH_COOKIE)?.value;
  if (!refresh) {
    authDiagnosticLog("info", "bff", "auth.bootstrap.refresh_cookie_missing", { request_id: requestId });
    return failureEnvelope(401, "登录已失效", requestId);
  }
  const startedAt = Date.now();
  authDiagnosticLog("info", "bff", "auth.bootstrap.started", { request_id: requestId, session_class: "web" });
  let tokenResult: Awaited<ReturnType<typeof callSparkUpstream>>;
  try {
    tokenResult = await callSparkUpstream("/api/v1/auth/token/refresh/", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) }, requestId);
  } catch (cause) {
    authDiagnosticLog("error", "bff", "auth.bootstrap.upstream_unreachable", { request_id: requestId, duration_ms: Date.now() - startedAt, error_type: cause instanceof Error ? cause.name : typeof cause });
    return failureEnvelope(503, "本地服务连接失败", requestId);
  }
  if (!tokenResult.response.ok) {
    authDiagnosticLog("warn", "bff", "auth.bootstrap.refresh_failed", { request_id: requestId, duration_ms: Date.now() - startedAt, http_status: tokenResult.response.status });
    return jsonEnvelope(tokenResult.body, tokenResult.response.status || 401, requestId);
  }
  const tokenData = refreshTokenDataFromUpstream(tokenResult.body);
  if (!tokenData) return failureEnvelope(502, "刷新响应缺少令牌", requestId);
  const access = stringField(tokenData.access_token, 4096);
  const rotated = stringField(tokenData.refresh_token, 4096) || refresh;
  if (!access) return failureEnvelope(502, "刷新响应缺少令牌", requestId);
  store.set(REFRESH_COOKIE, rotated, refreshCookieOptions());
  const sessionResult = await callSparkUpstream("/api/v1/auth/session/", { method: "GET", headers: { authorization: `Bearer ${access}` } }, requestId);
  if (!sessionResult.response.ok) return jsonEnvelope(sessionResult.body, sessionResult.response.status, requestId);
  const session = isRecord(sessionResult.body) ? sessionResult.body.data ?? null : null;
  authDiagnosticLog("info", "bff", "auth.bootstrap.succeeded", { request_id: requestId, duration_ms: Date.now() - startedAt });
  return jsonEnvelope({ code: 0, msg: "ok", data: { access_token: access, expires_in: tokenData.expires_in, token_type: tokenData.token_type || "Bearer", session } }, sessionResult.response.status, requestId);
}
