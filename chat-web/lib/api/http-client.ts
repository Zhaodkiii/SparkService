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
    "auth.unauthorized": "登录状态已失效，请重新登录。",
  };
  return messages[failure.messageKey] ?? (failure.httpStatus >= 500 ? "服务暂时不可用，请稍后重试。" : "请求未完成，请稍后重试。");
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
    if (options.body !== undefined) {
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
