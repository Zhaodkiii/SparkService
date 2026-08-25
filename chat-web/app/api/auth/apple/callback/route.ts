import { cookies } from "next/headers";
import { randomUUID } from "node:crypto";
import { NextResponse } from "next/server";
import { APPLE_NONCE_COOKIE, APPLE_RETURN_COOKIE, APPLE_STATE_COOKIE, REFRESH_COOKIE, clearCookieOptions, refreshCookieOptions } from "@/lib/server/auth-cookies";
import { callSparkUpstream, isRecord, requestIdFrom, stringField } from "@/lib/server/upstream";

function redirectWithError(path: string, code: string, origin: string) {
  const url = new URL(path, "http://spark.local");
  url.searchParams.set("error", code);
  return NextResponse.redirect(new URL(`${url.pathname}${url.search}`, origin));
}

function safePath(value: string | undefined) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/chat";
}

export async function POST(request: Request) {
  const requestId = requestIdFrom(request);
  const store = await cookies();
  const stateCookie = store.get(APPLE_STATE_COOKIE)?.value;
  const nonce = store.get(APPLE_NONCE_COOKIE)?.value;
  const returnTo = safePath(store.get(APPLE_RETURN_COOKIE)?.value);
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
    return redirectWithError(returnTo, "apple_callback_invalid", new URL(request.url).origin);
  }
  const state = fields.get("state");
  const identityToken = fields.get("id_token") || fields.get("identity_token");
  if (!stateCookie || !nonce || !state || state !== stateCookie || !identityToken) return redirectWithError(returnTo, "apple_callback_invalid", new URL(request.url).origin);
  const result = await callSparkUpstream("/api/v1/auth/apple/login/", { method: "POST", body: JSON.stringify({ identity_token: identityToken, authorization_code: fields.get("code") || undefined, nonce, bundle_id: process.env.SPARK_WEB_SERVICE_ID || "", device_id: randomUUID(), user: fields.get("user") || undefined }) }, requestId);
  if (!result.response.ok || !isRecord(result.body) || !isRecord(result.body.data) || typeof result.body.data.refresh_token !== "string") return redirectWithError(returnTo, "apple_login_failed", new URL(request.url).origin);
  const response = NextResponse.redirect(new URL(returnTo, new URL(request.url).origin));
  response.cookies.set(REFRESH_COOKIE, result.body.data.refresh_token, refreshCookieOptions());
  response.cookies.set(APPLE_STATE_COOKIE, "", clearCookieOptions());
  response.cookies.set(APPLE_NONCE_COOKIE, "", clearCookieOptions());
  response.cookies.set(APPLE_RETURN_COOKIE, "", clearCookieOptions());
  response.headers.set("cache-control", "no-store");
  response.headers.set("x-request-id", requestId);
  return response;
}
