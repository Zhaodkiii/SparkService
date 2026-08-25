import type { SparkHttpClient } from "@/lib/api/http-client";
import type { ContextSummaryDTO } from "@/types/run";
import type { ThreadPreferencesDTO } from "@/types/context";

function segment(value: string): string { return encodeURIComponent(value); }

export class SparkContextApi {
  constructor(private readonly http: SparkHttpClient) {}

  getPreferences(threadId: string): Promise<ThreadPreferencesDTO> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/threads/${segment(threadId)}/preferences/`);
  }

  updatePreferences(threadId: string, revision: number, patch: Partial<ThreadPreferencesDTO>): Promise<ThreadPreferencesDTO> {
    return this.http.requestOrThrow("PATCH", `/api/v1/ai/chat/threads/${segment(threadId)}/preferences/`, {
      body: { ...patch, revision },
      headers: { "If-Match": `"${revision}"` },
    });
  }

  getSummary(runId: string): Promise<ContextSummaryDTO> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/runs/${segment(runId)}/context-summary/`);
  }
}
