import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { REFRESH_COOKIE } from "@/lib/server/auth-cookies";

/**
 * Web 入口只根据 HttpOnly refresh cookie 做快速分流。
 * Cookie 是否仍然有效由 /home 内的 AuthGate + bootstrap 再做服务端校验。
 */
export default async function HomePage() {
  const cookieStore = await cookies();
  if (cookieStore.has(REFRESH_COOKIE)) {
    // `/home` is served by the optional catch-all route `/home/[[...threadId]]`.
    // Next typedRoutes currently cannot infer its empty catch-all form.
    redirect("/home" as never);
  }
  redirect("/login");
}
