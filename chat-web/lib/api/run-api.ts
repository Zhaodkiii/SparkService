import type { SparkHttpClient } from "@/lib/api/http-client";
import type { ChatRunDTO } from "@/types/chat";
import type { CreateRunData, CreateRunRequestDTO, RunEventsData, WebSocketTicketData } from "@/types/run";

function pathSegment(value: string): string {
  return encodeURIComponent(value);
}

export class SparkRunApi {
  constructor(private readonly http: SparkHttpClient) {}

  create(threadId: string, payload: CreateRunRequestDTO, idempotencyKey: string): Promise<CreateRunData> {
    return this.http.requestOrThrow("POST", `/api/v1/ai/chat/threads/${pathSegment(threadId)}/runs/`, {
      body: payload,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }

  getActive(threadId: string): Promise<{ run: ChatRunDTO | null }> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/threads/${pathSegment(threadId)}/active-run/`);
  }

  get(runId: string): Promise<{ run: ChatRunDTO }> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/runs/${pathSegment(runId)}/`);
  }

  events(runId: string, afterSequence = 0, limit = 200): Promise<RunEventsData> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/runs/${pathSegment(runId)}/events/?after_sequence=${afterSequence}&limit=${limit}`);
  }

  cancel(runId: string): Promise<{ run: ChatRunDTO }> {
    return this.http.requestOrThrow("POST", `/api/v1/ai/chat/runs/${pathSegment(runId)}/cancel/`);
  }

  regenerate(runId: string, idempotencyKey: string): Promise<CreateRunData> {
    return this.http.requestOrThrow("POST", `/api/v1/ai/chat/runs/${pathSegment(runId)}/regenerate/`, {
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }

  createWebSocketTicket(): Promise<WebSocketTicketData> {
    return this.http.requestOrThrow("POST", "/api/v1/ai/chat/ws-tickets/");
  }
}
