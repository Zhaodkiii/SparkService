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
  40098: "chat.image_capability_unavailable",
  40099: "chat.image_count_exceeded",
  40100: "chat.image_format_invalid",
  40201: "chat.image_not_ready",
  40202: "chat.image_registration_failed",
  40492: "chat.image_not_found",
  40980: "chat.run_idempotency_pending",
  50396: "chat.image_upload_unavailable",
  40102: "auth.token_invalid",
  40103: "auth.user_inactive",
  40124: "auth.apple_nonce_mismatch",
  40321: "auth.apple.configuration_error",
  40411: "auth.otp.not_found",
  40491: "chat.resource_not_found",
  40991: "chat.run_already_active",
  40992: "chat.idempotency_conflict",
  40097: "chat.interaction_idempotency_required",
  40494: "chat.interaction_not_found",
  40994: "chat.interaction_already_claimed",
  40995: "chat.interaction_claim_not_supported",
  40996: "chat.interaction_claim_invalid",
  40997: "chat.interaction_conflict",
  40998: "chat.interaction_already_resolved",
  40999: "chat.interaction_run_not_waiting",
  41094: "chat.interaction_expired",
  42296: "chat.interaction_response_invalid",
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
  40381: "hospital.doctor_profile_not_active",
  40383: "hospital.membership_required",
  40385: "hospital.conversation_not_assigned",
  40485: "hospital.conversation_not_found",
  40987: "hospital.agent_version_conflict",
  40989: "hospital.conversation_ended",
  40990: "hospital.conversation_version_conflict",
  40083: "hospital.idempotency_key_required",
};

const HOSPITAL_ERROR_KEYS: Record<string, string> = {
  HOSPITAL_MEMBERSHIP_REQUIRED: "hospital.membership_required",
  DOCTOR_PROFILE_NOT_ACTIVE: "hospital.doctor_profile_not_active",
  CONVERSATION_NOT_ASSIGNED: "hospital.conversation_not_assigned",
  CONVERSATION_NOT_JOINED: "hospital.conversation_not_joined",
  IMAGE_COUNT_EXCEEDED: "hospital.image_count_exceeded",
  IMAGE_FORMAT_INVALID: "hospital.image_format_invalid",
  IMAGE_NOT_FOUND: "hospital.image_not_found",
  CONVERSATION_NOT_FOUND: "hospital.conversation_not_found",
  CONVERSATION_ENDED: "hospital.conversation_ended",
  CONVERSATION_VERSION_CONFLICT: "hospital.conversation_version_conflict",
  AGENT_VERSION_CONFLICT: "hospital.agent_version_conflict",
  IDEMPOTENCY_CONFLICT: "hospital.idempotency_conflict",
  IDEMPOTENCY_KEY_REQUIRED: "hospital.idempotency_key_required",
  ATTACHMENT_TYPE_UNSUPPORTED: "hospital.attachment_type_unsupported",
  ATTACHMENT_SIZE_LIMIT: "hospital.attachment_size_limit",
  ATTACHMENT_COUNT_LIMIT: "hospital.attachment_count_limit",
  ATTACHMENT_UPLOAD_FAILED: "hospital.attachment_upload_failed",
  ATTACHMENT_NOT_FOUND: "hospital.attachment_not_found",
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

export function messageKeyForApiError(code: number, status: number, details?: unknown): string {
  if (isRecord(details) && typeof details.error_code === "string" && HOSPITAL_ERROR_KEYS[details.error_code]) {
    return HOSPITAL_ERROR_KEYS[details.error_code];
  }
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
    messageKey: messageKeyForApiError(envelope.code, response.status, details),
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
