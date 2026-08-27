import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { APPLE_NONCE_COOKIE, APPLE_RETURN_COOKIE, APPLE_STATE_COOKIE, REFRESH_COOKIE, clearCookieOptions, refreshCookieOptions } from "@/lib/server/auth-cookies";
import { appleWebUpstreamError } from "@/lib/auth/apple-web-errors";
import { authDiagnosticLog } from "@/lib/auth/diagnostics";
import { publicWebOrigin } from "@/lib/server/public-origin";
import { callSparkUpstream, isRecord, requestIdFrom } from "@/lib/server/upstream";

/**
 * Chat Web Apple callback（CHAT-WEB-019E）。
 *
 * 只调用 Web 专属上游 POST /api/v1/auth/apple/web/login/，绝不回退移动端
 * /api/v1/auth/apple/login/，也绝不生成/提交 device_id 或 bundle_id。
 * state/nonce 由短期 HttpOnly Cookie 单次消费；失败按服务端错误契约映射到
 * /login?error=<code>，由登录页展示对应文案与下一步动作。
 */

const LOGIN_PAGE = "/login";

function redirectWithError(errorCode: string, origin: string, requestId: string, returnTo: string) {
  const url = new URL(LOGIN_PAGE, origin);
  url.searchParams.set("error", errorCode);
  if (returnTo && returnTo !== "/chat") url.searchParams.set("return_to", returnTo);
  const response = NextResponse.redirect(url);
  response.headers.set("cache-control", "no-store");
  response.headers.set("x-request-id", requestId);
  return response;
}

function upstreamErrorCode(body: unknown): string {
  return appleWebUpstreamError(isRecord(body) ? (body as { code?: unknown }) : null);
}

function safePath(value: string | undefined) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/chat";
}

export async function POST(request: Request) {
  const requestId = requestIdFrom(request);
  const origin = publicWebOrigin(request);
  const store = await cookies();
  const stateCookie = store.get(APPLE_STATE_COOKIE)?.value;
  const nonce = store.get(APPLE_NONCE_COOKIE)?.value;
  const returnTo = safePath(store.get(APPLE_RETURN_COOKIE)?.value);
  authDiagnosticLog("info", "bff", "auth.apple.web.callback.received", {
    request_id: requestId,
    request_origin: origin,
    content_type: request.headers.get("content-type") || "",
    has_state_cookie: Boolean(stateCookie),
    has_nonce_cookie: Boolean(nonce),
    has_return_cookie: Boolean(store.get(APPLE_RETURN_COOKIE)?.value),
    user_agent_present: Boolean(request.headers.get("user-agent")),
  });

  // state/nonce 单次消费：Cookie 缺失即视为已消费（重放）或过期。
  const consumed = (code: string) => {
    authDiagnosticLog("warn", "bff", "auth.apple.web.callback.redirected_error", {
      request_id: requestId,
      error_code: code,
      return_to: returnTo,
      had_state_cookie: Boolean(stateCookie),
      had_nonce_cookie: Boolean(nonce),
    });
    const response = redirectWithError(code, origin, requestId, returnTo);
    response.cookies.set(APPLE_STATE_COOKIE, "", clearCookieOptions());
    response.cookies.set(APPLE_NONCE_COOKIE, "", clearCookieOptions());
    response.cookies.set(APPLE_RETURN_COOKIE, "", clearCookieOptions());
    return response;
  };

  let fields = new Map<string, string>();
  try {
    const type = request.headers.get("content-type") || "";
    if (type.includes("application/json")) {
      const raw = await request.json();
      if (isRecord(raw)) for (const [key, value] of Object.entries(raw)) if (typeof value === "string") fields.set(key, value);
    } else {
      const form = await request.formData();
      for (const [key, value] of form.entries()) if (typeof value === "string") fields.set(key, value);
    }
  } catch {
    authDiagnosticLog("warn", "bff", "auth.apple.web.callback.body_unreadable", { request_id: requestId });
    return consumed("apple_web_callback_invalid");
  }

  const state = fields.get("state");
  const identityToken = fields.get("id_token") || fields.get("identity_token");
  // 用户在 Apple 弹窗点取消：无 code/id_token，回登录页但不当作错误重试提示。
  if (fields.get("error") === "user_cancelled_authorize" || (!identityToken && !fields.get("code"))) {
    authDiagnosticLog("info", "bff", "auth.apple.web.callback.user_cancelled", { request_id: requestId });
    return consumed("apple_web_user_cancelled");
  }
  if (!stateCookie) {
    authDiagnosticLog("warn", "bff", "auth.apple.web.callback.state_cookie_missing", { request_id: requestId, has_state_field: Boolean(state), has_identity_token: Boolean(identityToken), has_code: Boolean(fields.get("code")) });
    return consumed("apple_web_transaction_replayed");
  }
  if (!nonce || !state || state !== stateCookie || !identityToken) {
    authDiagnosticLog("warn", "bff", "auth.apple.web.callback.state_nonce_rejected", {
      request_id: requestId,
      has_nonce_cookie: Boolean(nonce),
      has_state_field: Boolean(state),
      state_matches: Boolean(state && stateCookie && state === stateCookie),
      has_identity_token: Boolean(identityToken),
      has_code: Boolean(fields.get("code")),
    });
    return consumed("apple_web_callback_invalid");
  }

  const serviceId = process.env.SPARK_WEB_SERVICE_ID || "";
  const redirectUri = process.env.SPARK_APPLE_WEB_REDIRECT_URI || "";
  if (!serviceId || !redirectUri) {
    authDiagnosticLog("error", "bff", "auth.apple.web.callback.config_missing", { request_id: requestId });
    return consumed("apple_web_login_unavailable");
  }
  authDiagnosticLog("info", "bff", "auth.apple.web.callback.validated", { request_id: requestId, service_id: serviceId, redirect_uri: redirectUri, has_authorization_code: Boolean(fields.get("code")), has_user_field: Boolean(fields.get("user")) });

  const startedAt = Date.now();
  const result = await callSparkUpstream(
    "/api/v1/auth/apple/web/login/",
    {
      method: "POST",
      body: JSON.stringify({
        identity_token: identityToken,
        authorization_code: fields.get("code") || undefined,
        nonce,
        service_id: serviceId,
        redirect_uri: redirectUri,
        user: fields.get("user") || undefined,
      }),
    },
    requestId,
  );
  if (!result.response.ok || !isRecord(result.body) || !isRecord(result.body.data) || typeof result.body.data.refresh_token !== "string") {
    authDiagnosticLog("warn", "bff", "auth.apple.web.callback.login_failed", {
      request_id: requestId,
      duration_ms: Date.now() - startedAt,
      http_status: result.response.status,
      upstream_code: isRecord(result.body) && typeof result.body.code === "number" ? result.body.code : null,
    });
    return consumed(upstreamErrorCode(result.body));
  }

  const response = NextResponse.redirect(new URL(returnTo, origin));
  response.cookies.set(REFRESH_COOKIE, result.body.data.refresh_token, refreshCookieOptions());
  response.cookies.set(APPLE_STATE_COOKIE, "", clearCookieOptions());
  response.cookies.set(APPLE_NONCE_COOKIE, "", clearCookieOptions());
  response.cookies.set(APPLE_RETURN_COOKIE, "", clearCookieOptions());
  response.headers.set("cache-control", "no-store");
  response.headers.set("x-request-id", requestId);
  authDiagnosticLog("info", "bff", "auth.apple.web.callback.succeeded", { request_id: requestId, duration_ms: Date.now() - startedAt });
  return response;
}
