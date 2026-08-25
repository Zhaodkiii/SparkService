import { SparkApiError } from "@/lib/api/http-client";

const MAINLAND_MOBILE = /^1\d{10}$/;
const DEVICE_STORAGE_KEY = "spark.web.device-id.v1";

export function normalizeMainlandPhone(value: string): string | null {
  const digits = value.replace(/\D/g, "");
  const local = digits.startsWith("86") && digits.length === 13 ? digits.slice(2) : digits;
  return MAINLAND_MOBILE.test(local) ? `+86${local}` : null;
}

export function getOrCreateWebDeviceId(): string {
  const existing = window.localStorage.getItem(DEVICE_STORAGE_KEY)?.trim();
  if (existing) return existing;
  const id = typeof crypto.randomUUID === "function"
    ? `web-${crypto.randomUUID()}`
    : `web-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  window.localStorage.setItem(DEVICE_STORAGE_KEY, id);
  return id;
}

export function phoneOtpErrorMessage(cause: unknown, action: "request" | "verify"): string {
  if (!(cause instanceof SparkApiError)) return "无法连接本地服务，请确认 Web 与服务端均已启动";
  const messages: Record<number, string> = {
    40031: "请输入手机号",
    40032: "请输入正确的中国大陆手机号",
    40033: "当前手机号地区暂不支持短信登录",
    40041: "验证码已使用，请重新获取",
    40042: "验证码已过期，请重新获取",
    40043: "验证码不正确",
    40044: "登录客户端不匹配，请重新获取验证码",
    40045: "验证码已失效，请重新获取",
    40046: "短信未成功发送，请重新获取",
    40411: "验证码记录不存在，请重新获取",
    42311: "验证码尝试次数过多，请稍后再试",
    42901: "发送过于频繁，请稍后再试",
    42902: "短信服务触发频率限制，请稍后再试",
    50231: "短信服务发送失败，请稍后重试",
    50331: "短信服务暂时无响应，请稍后重试",
    50301: "本地服务暂不可用，请确认 Django 服务已启动",
    [-1]: "浏览器未能发出请求，请检查网络或开发者控制台",
  };
  return messages[cause.failure.code]
    ?? (action === "request" ? "验证码请求失败，请稍后重试" : "验证码错误或已过期");
}
