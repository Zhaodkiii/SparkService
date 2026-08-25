import { randomUUID } from "node:crypto";

const DEFAULT_INTERNAL_API = "http://127.0.0.1:2026";

export function internalApiBaseUrl() {
  return (process.env.SPARK_INTERNAL_API_BASE_URL || DEFAULT_INTERNAL_API).replace(/\/$/, "");
}

export function requestIdFrom(request: Request) {
  return request.headers.get("x-request-id") || randomUUID();
}

export async function callSparkUpstream(path: string, init: RequestInit = {}, requestId: string = randomUUID()) {
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  headers.set("x-request-id", requestId);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const response = await fetch(`${internalApiBaseUrl()}${path}`, { ...init, headers, cache: "no-store" });
  const text = await response.text();
  let body: unknown = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = null; }
  return { response, body, requestId };
}

export function jsonEnvelope(body: unknown, status: number, requestId: string, extraHeaders?: HeadersInit) {
  const headers = new Headers(extraHeaders);
  headers.set("content-type", "application/json; charset=utf-8");
  headers.set("cache-control", "no-store");
  headers.set("x-request-id", requestId);
  return new Response(JSON.stringify(body), { status, headers });
}

export function failureEnvelope(status: number, message = "服务暂不可用", requestId: string = randomUUID()) {
  return jsonEnvelope({ code: status >= 500 ? 50301 : status, msg: message, data: null }, status, requestId);
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

export function stringField(value: unknown, max = 512) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= max ? value.trim() : null;
}

export function upstreamResponse(result: Awaited<ReturnType<typeof callSparkUpstream>>) {
  const body = isRecord(result.body) ? result.body : { code: 50301, msg: "上游响应格式错误", data: null };
  return jsonEnvelope(body, result.response.status, result.requestId);
}
