import type { SparkHttpClient } from "@/lib/api/http-client";
import type { InteractionCommandData, InteractionSubmitBody, PendingInteractionDTO } from "@/types/interaction";

function pathSegment(value: string): string {
  return encodeURIComponent(value);
}

export class SparkInteractionApi {
  constructor(private readonly http: SparkHttpClient) {}

  getPendingForRun(runId: string): Promise<{ interactions: PendingInteractionDTO[] }> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/runs/${pathSegment(runId)}/interactions/pending/`);
  }

  get(interactionId: string): Promise<{ interaction: PendingInteractionDTO }> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/interactions/${pathSegment(interactionId)}/`);
  }

  submitResponse(interactionId: string, response: InteractionSubmitBody, idempotencyKey: string): Promise<InteractionCommandData> {
    return this.http.requestOrThrow("POST", `/api/v1/ai/chat/interactions/${pathSegment(interactionId)}/responses/`, {
      body: { response },
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }

  refuse(interactionId: string, reason: string, idempotencyKey: string, deviceId = ""): Promise<InteractionCommandData> {
    return this.http.requestOrThrow("POST", `/api/v1/ai/chat/interactions/${pathSegment(interactionId)}/refuse/`, {
      body: { reason, device_id: deviceId },
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }
}
