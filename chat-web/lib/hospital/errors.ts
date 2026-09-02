import { SparkApiError } from "@/lib/api/http-client";

const MESSAGE_KEY_TO_CODE: Record<string, string> = {
  "hospital.membership_required": "HOSPITAL_MEMBERSHIP_REQUIRED",
  "hospital.doctor_profile_not_active": "DOCTOR_PROFILE_NOT_ACTIVE",
  "hospital.conversation_not_assigned": "CONVERSATION_NOT_ASSIGNED",
  "hospital.conversation_not_found": "CONVERSATION_NOT_FOUND",
  "hospital.conversation_ended": "CONVERSATION_ENDED",
  "hospital.conversation_version_conflict": "CONVERSATION_VERSION_CONFLICT",
  "hospital.agent_version_conflict": "AGENT_VERSION_CONFLICT",
  "hospital.idempotency_conflict": "IDEMPOTENCY_CONFLICT",
  "hospital.idempotency_key_required": "IDEMPOTENCY_KEY_REQUIRED",
};

export function hospitalErrorCode(error: unknown): string {
  if (error instanceof SparkApiError) {
    const details = error.failure.details;
    if (details && typeof details === "object" && "error_code" in details && typeof details.error_code === "string") {
      return details.error_code;
    }
    return MESSAGE_KEY_TO_CODE[error.failure.messageKey] ?? error.failure.messageKey;
  }
  return error instanceof Error ? error.message : "";
}

export function isHospitalError(error: unknown, code: string): boolean {
  return hospitalErrorCode(error) === code;
}

export function hospitalErrorMessage(error: unknown): string {
  if (error instanceof SparkApiError) return error.message;
  return error instanceof Error ? error.message : "请求失败";
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export function isUnauthorizedDoctor(error: unknown): boolean {
  if (!(error instanceof SparkApiError)) return false;
  if (error.failure.httpStatus === 403) return true;
  const code = hospitalErrorCode(error);
  return code === "HOSPITAL_MEMBERSHIP_REQUIRED" || code === "DOCTOR_PROFILE_NOT_ACTIVE";
}
