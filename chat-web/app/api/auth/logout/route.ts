import { cookies } from "next/headers";
import { REFRESH_COOKIE, clearCookieOptions } from "@/lib/server/auth-cookies";
import { callSparkUpstream, jsonEnvelope, requestIdFrom } from "@/lib/server/upstream";

export async function POST(request: Request) {
  const requestId = requestIdFrom(request);
  const authorization = request.headers.get("authorization");
  let result: Awaited<ReturnType<typeof callSparkUpstream>> | null = null;
  if (authorization?.startsWith("Bearer ")) result = await callSparkUpstream("/api/v1/auth/logout/", { method: "POST", headers: { authorization } }, requestId);
  const store = await cookies();
  store.set(REFRESH_COOKIE, "", clearCookieOptions());
  if (result && !result.response.ok) return jsonEnvelope(result.body, result.response.status, requestId);
  return jsonEnvelope({ code: 0, msg: "ok", data: {} }, 200, requestId);
}
