import { hospitalErrorCode, hospitalErrorMessage, isHospitalError } from "@/lib/hospital/errors";

export interface HospitalWriteResolution {
  code: string;
  message: string;
  retrySameKey: boolean;
  refetchDetail: boolean;
  dropConversation: boolean;
}

export function resolveHospitalWriteError(error: unknown): HospitalWriteResolution {
  const code = hospitalErrorCode(error);
  const message = hospitalErrorMessage(error);
  if (isHospitalError(error, "CONVERSATION_NOT_ASSIGNED") || code === "CONVERSATION_NOT_ASSIGNED") {
    return { code: "CONVERSATION_NOT_ASSIGNED", message, retrySameKey: false, refetchDetail: false, dropConversation: true };
  }
  if (isHospitalError(error, "CONVERSATION_VERSION_CONFLICT") || code === "CONVERSATION_VERSION_CONFLICT") {
    return { code: "CONVERSATION_VERSION_CONFLICT", message, retrySameKey: false, refetchDetail: true, dropConversation: false };
  }
  if (isHospitalError(error, "CONVERSATION_ENDED") || code === "CONVERSATION_ENDED") {
    return { code: "CONVERSATION_ENDED", message, retrySameKey: false, refetchDetail: true, dropConversation: false };
  }
  if (isHospitalError(error, "IDEMPOTENCY_CONFLICT") || code === "IDEMPOTENCY_CONFLICT") {
    return { code: "IDEMPOTENCY_CONFLICT", message, retrySameKey: false, refetchDetail: false, dropConversation: false };
  }
  return { code, message, retrySameKey: true, refetchDetail: false, dropConversation: false };
}
