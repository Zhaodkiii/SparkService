import { callSparkUpstream, jsonEnvelope, requestIdFrom } from "@/lib/server/upstream";

export async function GET(request: Request) {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) return jsonEnvelope({ code: 40102, msg: "登录已失效", data: null }, 401, requestIdFrom(request));
  const requestId = requestIdFrom(request);
  const result = await callSparkUpstream("/api/v1/auth/session/", { method: "GET", headers: { authorization } }, requestId);
  return jsonEnvelope(result.body, result.response.status, requestId);
}
