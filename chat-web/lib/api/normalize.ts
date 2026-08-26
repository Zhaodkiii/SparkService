import type { SparkApiEnvelope, SparkApiFailure, SparkApiSuccess } from "@/types/api";

const BUSINESS_MESSAGE_KEYS: Record<number, string> = {
  40031: "auth.phone.required",
  40032: "auth.phone.invalid",
  40033: "auth.phone.region_not_supported",
  40011: "auth.otp.used",
  40012: "auth.otp.expired",
  40013: "auth.otp.invalid",
  40041: "auth.otp.used",
  40042: "auth.otp.expired",
  40043: "auth.otp.invalid",
  40044: "auth.client_mismatch",
  40045: "auth.otp.unavailable",
  40046: "auth.otp.delivery_failed",
  40091: "chat.request_invalid",
  40094: "chat.context_invalid",
  40102: "auth.token_invalid",
  40103: "auth.user_inactive",
  40124: "auth.apple_nonce_mismatch",
  40321: "auth.apple.configuration_error",
  40411: "auth.otp.not_found",
  40491: "chat.resource_not_found",
  40991: "chat.run_already_active",
  40992: "chat.idempotency_conflict",
  40993: "chat.preferences_conflict",
  42301: "auth.otp.locked",
  42311: "auth.otp.locked",
  42901: "auth.otp.rate_limited",
  42902: "auth.sms.rate_limited",
  50231: "auth.sms.send_failed",
  50301: "api.server_unavailable",
  50331: "auth.sms.unavailable",
  50392: "chat.server_runs_disabled",
  50393: "chat.run_executor_unavailable",
  50394: "chat.run_model_binding_missing",
  50395: "chat.run_worker_unavailable",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isEnvelope(value: unknown): value is SparkApiEnvelope {
  return isRecord(value) && typeof value.code === "number" && "msg" in value && "data" in value;
}

function readRequestId(response: Pick<Response, "headers">, envelope?: SparkApiEnvelope): string | undefined {
  const header = response.headers.get("x-request-id") || response.headers.get("x-correlation-id");
  if (header) return header;
  if (isRecord(envelope?.data) && typeof envelope.data.request_id === "string") return envelope.data.request_id;
  return undefined;
}

function messageText(msg: SparkApiEnvelope["msg"]): string | undefined {
  if (typeof msg === "string" && msg.trim()) return msg;
  if (isRecord(msg)) {
    const first = Object.values(msg).find((value) => typeof value === "string" && value.trim());
    return typeof first === "string" ? first : undefined;
  }
  return undefined;
}

function retryableFor(status: number, details: unknown): boolean {
  if (isRecord(details) && details.retryable === false) return false;
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

export function messageKeyForApiError(code: number, status: number): string {
  return BUSINESS_MESSAGE_KEYS[code] ?? (status >= 500 ? "api.server_error" : status === 401 ? "auth.unauthorized" : "api.request_failed");
}

export function failureFromEnvelope(
  response: Pick<Response, "status" | "headers">,
  envelope: SparkApiEnvelope,
): SparkApiFailure {
  const details = envelope.data;
  return {
    ok: false,
    httpStatus: response.status,
    code: envelope.code,
    messageKey: messageKeyForApiError(envelope.code, response.status),
    message: messageText(envelope.msg),
    details,
    requestId: readRequestId(response, envelope),
    retryable: retryableFor(response.status, details),
  };
}

export function successFromEnvelope<TData>(response: Pick<Response, "status" | "headers">, envelope: SparkApiEnvelope<TData>): SparkApiSuccess<TData> {
  return {
    ok: true,
    data: envelope.data as TData,
    httpStatus: response.status,
    requestId: readRequestId(response, envelope),
  };
}

export async function readJsonBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text.trim()) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

export function normalizeResponse<TData>(response: Pick<Response, "status" | "headers">, body: unknown): SparkApiSuccess<TData> | SparkApiFailure {
  if (!isEnvelope(body)) {
    return {
      ok: false,
      httpStatus: response.status,
      code: -1,
      messageKey: "api.invalid_envelope",
      message: "Invalid Spark API response",
      requestId: readRequestId(response),
      retryable: response.status >= 500,
    };
  }
  if (body.code !== 0 || response.status < 200 || response.status >= 300) return failureFromEnvelope(response, body);
  return successFromEnvelope(response, body as SparkApiEnvelope<TData>);
}
