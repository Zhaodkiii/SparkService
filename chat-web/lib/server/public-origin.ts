/**
 * 计算对浏览器可见的公网站点 Origin。
 *
 * OAuth 回调后的重定向必须以公网域名为准，不能依赖 `request.url` 推断：
 * 生产反代环境下 Next.js standalone 可能把自身监听地址（如 0.0.0.0:9001）
 * 当成请求 Origin，导致失败回跳地址错误。
 */

const INTERNAL_HOSTS = new Set(["0.0.0.0", "127.0.0.1", "localhost", "::1"]);

export function publicWebOrigin(request: { url: string }): string {
  const configured = (process.env.SPARK_PUBLIC_WEB_BASE_URL || "").trim().replace(/\/+$/, "");
  if (configured) {
    try {
      const origin = new URL(configured).origin;
      if (process.env.NODE_ENV === "production" && INTERNAL_HOSTS.has(new URL(origin).hostname)) {
        console.error(`[chat-web] SPARK_PUBLIC_WEB_BASE_URL 指向内部地址 ${new URL(origin).hostname}，浏览器重定向将不可访问`);
      }
      return origin;
    } catch {
      console.error("[chat-web] SPARK_PUBLIC_WEB_BASE_URL 不是合法 URL，已回退到请求 Origin");
    }
  }
  return new URL(request.url).origin;
}