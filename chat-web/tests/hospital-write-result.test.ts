import { describe, expect, it } from "vitest";
import { SparkApiError } from "@/lib/api/http-client";
import { newIdempotencyKey } from "@/lib/hospital/errors";
import { resolveHospitalWriteError } from "@/lib/hospital/write-result";
import { failureFromEnvelope } from "@/lib/api/normalize";

function hospitalError(errorCode: string, code: number, status: number) {
  return new SparkApiError(failureFromEnvelope(
    { status, headers: new Headers({ "x-request-id": "req-h" }) },
    { code, msg: errorCode, data: { error_code: errorCode } },
  ));
}

describe("hospital write conflict handling", () => {
  it("keeps the same idempotency key on ordinary failures", () => {
    const resolution = resolveHospitalWriteError(new Error("network"));
    expect(resolution.retrySameKey).toBe(true);
    expect(resolution.dropConversation).toBe(false);
    expect(resolution.refetchDetail).toBe(false);
  });

  it("refetches detail on version conflict and does not retry the stale key", () => {
    const resolution = resolveHospitalWriteError(hospitalError("CONVERSATION_VERSION_CONFLICT", 40990, 409));
    expect(resolution.code).toBe("CONVERSATION_VERSION_CONFLICT");
    expect(resolution.refetchDetail).toBe(true);
    expect(resolution.retrySameKey).toBe(false);
  });

  it("removes the card when the conversation is no longer assigned", () => {
    const resolution = resolveHospitalWriteError(hospitalError("CONVERSATION_NOT_ASSIGNED", 40385, 403));
    expect(resolution.dropConversation).toBe(true);
    expect(resolution.retrySameKey).toBe(false);
  });

  it("asks for a new idempotency key after an idempotency conflict", () => {
    const resolution = resolveHospitalWriteError(hospitalError("IDEMPOTENCY_CONFLICT", 40992, 409));
    expect(resolution.code).toBe("IDEMPOTENCY_CONFLICT");
    expect(resolution.retrySameKey).toBe(false);
  });

  it("does not reuse chat.idempotency_conflict for hospital 40992 without error_code", () => {
    const failure = failureFromEnvelope(
      { status: 409, headers: new Headers() },
      { code: 40992, msg: "chat_idempotency_conflict", data: { retryable: false } },
    );
    expect(failure.messageKey).toBe("chat.idempotency_conflict");
  });

  it("maps hospital error_code onto a dedicated message key", () => {
    const failure = failureFromEnvelope(
      { status: 409, headers: new Headers() },
      { code: 40992, msg: "idempotency_conflict", data: { error_code: "IDEMPOTENCY_CONFLICT" } },
    );
    expect(failure.messageKey).toBe("hospital.idempotency_conflict");
  });

  it("creates a unique idempotency key", () => {
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
  });
});
