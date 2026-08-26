/**
 * CHAT-WEB-019 6.6 错误契约的浏览器侧共享定义。
 *
 * - `appleWebUpstreamErrorByCode`：服务端业务码 → 浏览器可见 error code（callback 路由使用）。
 * - `appleWebErrorCopy`：error code → 登录页文案。
 * 两张表必须同步维护；未知 code 一律降级为通用文案，不暴露内部细节。
 */

export const APPLE_WEB_ERROR_QUERY = "error";

export const appleWebUpstreamErrorByCode: Record<number, string> = {
  40071: "apple_web_callback_invalid",
  40171: "apple_web_nonce_mismatch",
  40172: "apple_web_token_invalid",
  40971: "apple_web_transaction_replayed",
  40972: "apple_web_identity_link_required",
  50371: "apple_web_login_unavailable",
  50372: "apple_web_login_unavailable",
  50373: "apple_web_login_unavailable",
  50374: "apple_web_login_unavailable",
};

export const appleWebErrorCopy: Record<string, string> = {
  apple_web_callback_invalid: "登录状态校验未通过，请重新发起 Apple 登录。",
  apple_web_nonce_mismatch: "登录会话已失效，请重新发起 Apple 登录。",
  apple_web_token_invalid: "Apple 登录校验失败，请重试或改用手机号登录。",
  apple_web_transaction_replayed: "该登录请求已被使用，请重新发起登录。",
  apple_web_identity_link_required: "该 Apple 账号的邮箱已绑定其他账号，请先在原账号中完成绑定或改用手机号登录。",
  apple_web_login_unavailable: "Apple 登录服务暂时不可用，请稍后重试。",
  apple_web_user_cancelled: "已取消 Apple 登录。",
  apple_login_failed: "Apple 登录失败，请重试。",
};

export function appleWebErrorForCode(code: string): string {
  return appleWebErrorCopy[code] ?? "登录未完成，请重试。";
}

export function appleWebUpstreamError(body: { code?: unknown } | null | undefined): string {
  const code = body && typeof body.code === "number" ? body.code : null;
  return code !== null ? appleWebUpstreamErrorByCode[code] ?? "apple_web_token_invalid" : "apple_web_token_invalid";
}
