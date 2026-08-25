import { callSparkUpstream, failureEnvelope, jsonEnvelope, requestIdFrom } from "@/lib/server/upstream";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: RouteContext) {
  const { path } = await context.params;
  const upstreamPath = `/api/v1/${path.join("/")}`;
  const headers = new Headers();
  for (const name of ["authorization", "idempotency-key", "if-match", "x-device-id", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  const requestId = requestIdFrom(request);
  try {
    const result = await callSparkUpstream(upstreamPath, { method: request.method, headers, body }, requestId);
    return jsonEnvelope(result.body, result.response.status, result.requestId);
  } catch (cause) {
    console.warn("[SparkChat] api.proxy.upstream_unreachable", { request_id: requestId, path: upstreamPath, error_type: cause instanceof Error ? cause.name : typeof cause });
    return failureEnvelope(503, "服务连接失败", requestId);
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
