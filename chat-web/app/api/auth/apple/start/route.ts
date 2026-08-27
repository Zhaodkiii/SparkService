import { cookies } from "next/headers";
import { randomUUID } from "node:crypto";
import { APPLE_NONCE_COOKIE, APPLE_RETURN_COOKIE, APPLE_STATE_COOKIE, transientCookieOptions } from "@/lib/server/auth-cookies";
import { failureEnvelope, jsonEnvelope, requestIdFrom } from "@/lib/server/upstream";
import { authDiagnosticLog } from "@/lib/auth/diagnostics";
import { appleNonceDigest } from "@/lib/server/apple-nonce";
import { publicWebOrigin } from "@/lib/server/public-origin";

function safeReturnPath(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/chat";
}

export async function GET(request: Request) {
  const requestId = requestIdFrom(request);
  const authorizeUrl = process.env.SPARK_APPLE_AUTHORIZE_URL;
  const clientId = process.env.SPARK_WEB_SERVICE_ID;
  const redirectUri = process.env.SPARK_APPLE_WEB_REDIRECT_URI;
  authDiagnosticLog("info", "bff", "auth.apple.web.start.received", {
    request_id: requestId,
    has_authorize_url: Boolean(authorizeUrl),
    has_service_id: Boolean(clientId),
    has_redirect_uri: Boolean(redirectUri),
    request_origin: publicWebOrigin(request),
  });
  if (!authorizeUrl || !clientId || !redirectUri) {
    authDiagnosticLog("error", "bff", "auth.apple.web.start.config_missing", { request_id: requestId });
    return failureEnvelope(503, "Apple 登录暂未配置", requestId);
  }
  const url = new URL(request.url);
  const state = randomUUID();
  // Cookie 保存原始 nonce，Apple 接收其 SHA-256 值；Django 会按同一契约校验。
  const rawNonce = randomUUID();
  const appleNonce = appleNonceDigest(rawNonce);
  const authorize = new URL(authorizeUrl);
  authorize.searchParams.set("client_id", clientId);
  authorize.searchParams.set("redirect_uri", redirectUri);
  authorize.searchParams.set("response_type", "code id_token");
  authorize.searchParams.set("response_mode", "form_post");
  authorize.searchParams.set("scope", "name email");
  authorize.searchParams.set("state", state);
  authorize.searchParams.set("nonce", appleNonce);
  const store = await cookies();
  store.set(APPLE_STATE_COOKIE, state, transientCookieOptions());
  store.set(APPLE_NONCE_COOKIE, rawNonce, transientCookieOptions());
  store.set(APPLE_RETURN_COOKIE, safeReturnPath(url.searchParams.get("return_to")), transientCookieOptions());
  authDiagnosticLog("info", "bff", "auth.apple.web.start.issued", {
    request_id: requestId,
    service_id: clientId,
    redirect_uri: redirectUri,
    return_to: safeReturnPath(url.searchParams.get("return_to")),
    nonce_transform: "sha256_hex",
    cookie_mode: process.env.NODE_ENV === "production" ? "secure_none" : "lax_dev",
  });
  return jsonEnvelope({ code: 0, msg: "ok", data: { authorization_url: authorize.toString() } }, 200, requestId);
}
