import { cookies } from "next/headers";
import { randomUUID } from "node:crypto";
import { APPLE_NONCE_COOKIE, APPLE_RETURN_COOKIE, APPLE_STATE_COOKIE, transientCookieOptions } from "@/lib/server/auth-cookies";
import { failureEnvelope, jsonEnvelope, requestIdFrom } from "@/lib/server/upstream";

function safeReturnPath(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/chat";
}

export async function GET(request: Request) {
  const requestId = requestIdFrom(request);
  const authorizeUrl = process.env.SPARK_APPLE_AUTHORIZE_URL;
  const clientId = process.env.SPARK_WEB_SERVICE_ID;
  const redirectUri = process.env.SPARK_APPLE_WEB_REDIRECT_URI;
  if (!authorizeUrl || !clientId || !redirectUri) return failureEnvelope(503, "Apple 登录暂未配置", requestId);
  const url = new URL(request.url);
  const state = randomUUID();
  const nonce = randomUUID();
  const authorize = new URL(authorizeUrl);
  authorize.searchParams.set("client_id", clientId);
  authorize.searchParams.set("redirect_uri", redirectUri);
  authorize.searchParams.set("response_type", "code id_token");
  authorize.searchParams.set("response_mode", "form_post");
  authorize.searchParams.set("scope", "name email");
  authorize.searchParams.set("state", state);
  authorize.searchParams.set("nonce", nonce);
  const store = await cookies();
  store.set(APPLE_STATE_COOKIE, state, transientCookieOptions());
  store.set(APPLE_NONCE_COOKIE, nonce, transientCookieOptions());
  store.set(APPLE_RETURN_COOKIE, safeReturnPath(url.searchParams.get("return_to")), transientCookieOptions());
  return jsonEnvelope({ code: 0, msg: "ok", data: { authorization_url: authorize.toString() } }, 200, requestId);
}
