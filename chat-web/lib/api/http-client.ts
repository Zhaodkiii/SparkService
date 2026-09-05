import type { SparkApiFailure, SparkApiResult, SparkHttpClientOptions, SparkRequestOptions } from "@/types/api";
import { normalizeResponse, readJsonBody } from "@/lib/api/normalize";
import { clientErrorDetails, sparkClientLog } from "@/lib/diagnostics";

function makeRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `web-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function joinUrl(baseUrl: string | undefined, path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const base = baseUrl?.replace(/\/$/, "") ?? "";
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}${suffix}` || suffix;
}

export class SparkApiError extends Error {
  readonly failure: SparkApiFailure;

  constructor(failure: SparkApiFailure) {
    super(userFacingApiError(failure));
    this.name = "SparkApiError";
    this.failure = failure;
  }
}

export function userFacingApiError(failure: SparkApiFailure): string {
  const messages: Record<string, string> = {
    "api.network_error": "无法连接服务，请检查网络或前端 API 地址。",
    "chat.server_runs_disabled": "服务端对话尚未开启，请联系管理员。",
    "chat.run_executor_unavailable": "对话服务暂未就绪，请稍后再试。",
    "chat.run_model_binding_missing": "对话模型配置异常，请联系管理员。",
    "chat.run_worker_unavailable": "服务暂时繁忙，请稍后重试。",
    "chat.thread_not_found": "当前对话不存在或已失效，请刷新页面。",
    "chat.run_already_active": "当前对话仍在生成中，请稍候或先停止上一轮。",
    "chat.interaction_conflict": "这份回答与已提交内容冲突，已为你刷新当前状态。",
    "chat.interaction_already_resolved": "这个问题已经回答过了。",
    "chat.interaction_expired": "确认已过期，请等待小鲸继续。",
    "chat.interaction_response_invalid": "提交内容不完整，请重新选择后再试。",
    "chat.interaction_idempotency_required": "提交失败，请稍后重试。",
    "chat.image_capability_unavailable": "当前模型不支持图片理解，无法发送图片。",
    "chat.image_count_exceeded": "单条消息最多发送 3 张图片。",
    "chat.image_format_invalid": "图片格式或大小不符合要求，请更换图片。",
    "chat.image_not_ready": "图片尚未上传完成，请稍候再试。",
    "chat.image_registration_failed": "图片登记失败，请重试上传。",
    "chat.image_not_found": "图片不存在或已失效，请移除后重新选择。",
    "chat.image_upload_unavailable": "图片上传服务暂不可用，请稍后重试。",
    "chat.run_idempotency_pending": "相同消息仍在处理中，请稍候。",
    "auth.unauthorized": "登录状态已失效，请重新登录。",
    "hospital.membership_required": "当前账号没有医院职工身份，无法进入医生工作台。",
    "hospital.doctor_profile_not_active": "医生身份未激活，请联系医院管理员。",
    "hospital.conversation_not_assigned": "会话不在当前医生的授权范围内。",
    "hospital.conversation_not_found": "会话不存在或已失效。",
    "hospital.conversation_ended": "本次服务已结束，不能继续回复。",
    "hospital.conversation_version_conflict": "会话已被其他操作更新，请刷新后重试。",
    "hospital.agent_version_conflict": "智能体资料已被更新，请刷新后重试。",
    "hospital.idempotency_conflict": "相同请求正在处理，请确认后重试。",
    "hospital.idempotency_key_required": "请求缺少幂等键，请稍后重试。",
    "hospital.image_count_exceeded": "单条消息最多发送 3 张图片。",
    "hospital.image_format_invalid": "图片格式或大小不符合要求，请更换图片。",
    "hospital.image_not_found": "图片不存在或已失效，请移除后重新选择。",
    "hospital.conversation_not_joined": "请先接管问诊，再发送回复。",
    "hospital.attachment_type_unsupported": "附件类型不支持，仅支持 PDF、JPG、PNG。",
    "hospital.attachment_size_limit": "附件大小超出限制，请压缩后重试。",
    "hospital.attachment_count_limit": "附件数量超出限制，请减少后重试。",
    "hospital.attachment_upload_failed": "附件上传失败，请稍后重试。",
    "hospital.attachment_not_found": "附件不存在或已失效，请重新选择。",
  };
  return messages[failure.messageKey] ?? failure.message ?? (failure.httpStatus >= 500 ? "服务暂时不可用，请稍后重试。" : "请求未完成，请稍后重试。");
}

export class SparkHttpClient {
  private readonly baseUrl?: string;
  private readonly fetcher: typeof fetch;
  private readonly getAccessToken?: () => string | null;
  private readonly refreshAccessToken?: () => Promise<string | null>;

  constructor(options: SparkHttpClientOptions = {}) {
    this.baseUrl = options.baseUrl;
    this.fetcher = options.fetcher ?? fetch;
    this.getAccessToken = options.getAccessToken;
    this.refreshAccessToken = options.refreshAccessToken;
  }

  async request<TData>(method: string, path: string, options: SparkRequestOptions = {}): Promise<SparkApiResult<TData>> {
    return this.requestOnce<TData>(method, path, options, false);
  }

  async requestOrThrow<TData>(method: string, path: string, options: SparkRequestOptions = {}): Promise<TData> {
    const result = await this.request<TData>(method, path, options);
    if (!result.ok) throw new SparkApiError(result);
    return result.data;
  }

  private async requestOnce<TData>(method: string, path: string, options: SparkRequestOptions, retried: boolean): Promise<SparkApiResult<TData>> {
    const startedAt = Date.now();
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    headers.set("X-Request-ID", options.requestId ?? makeRequestId());
    const requestId = headers.get("X-Request-ID") || "-";
    sparkClientLog("info", "api.request.started", { method, path, request_id: requestId });
    const accessToken = this.getAccessToken?.();
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

    let body: BodyInit | undefined;
    if (options.rawBody !== undefined) {
      // 原始请求体（FormData 等）：不设置 Content-Type，交由浏览器生成边界。
      body = options.rawBody;
    } else if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(options.body);
    }

    let response: Response;
    try {
      // Browser native fetch rejects calls whose `this` is SparkHttpClient.
      // Detaching it from the instance preserves the native Window binding semantics.
      const fetcher = this.fetcher;
      response = await fetcher(joinUrl(this.baseUrl, path), {
        method,
        headers,
        body,
        signal: options.signal,
        credentials: "include",
        cache: "no-store",
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      sparkClientLog("error", "api.request.network_failed", { method, path, request_id: requestId, duration_ms: Date.now() - startedAt, ...clientErrorDetails(error) });
      return {
        ok: false,
        httpStatus: 0,
        code: -1,
        messageKey: "api.network_error",
        message: error instanceof Error ? error.message : undefined,
        retryable: true,
      };
    }

    const bodyJson = await readJsonBody(response);
    const result = normalizeResponse<TData>(response, bodyJson);
    if (result.ok) {
      sparkClientLog("info", "api.request.succeeded", { method, path, request_id: result.requestId || requestId, http_status: response.status, duration_ms: Date.now() - startedAt });
    } else {
      sparkClientLog(response.status >= 500 ? "error" : "warn", "api.request.failed", { method, path, request_id: result.requestId || requestId, http_status: response.status, business_code: result.code, duration_ms: Date.now() - startedAt, retryable: result.retryable });
    }
    if (!result.ok && response.status === 401 && !retried && options.retryOnUnauthorized !== false && this.refreshAccessToken) {
      const refreshed = await this.refreshAccessToken();
      if (refreshed) return this.requestOnce<TData>(method, path, options, true);
    }
    return result;
  }
}
