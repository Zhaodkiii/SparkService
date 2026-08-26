import type { SparkHttpClient } from "@/lib/api/http-client";
import type { ThreadPreferencesDTO, ThreadPreferencesUpdateDTO, ToolCatalogDTO } from "@/types/tool";

export interface ToolCatalogLoadResult {
  catalog: ToolCatalogDTO | null;
  error: string | null;
}

export class SparkToolCatalogApi {
  constructor(private readonly http: SparkHttpClient) {}

  catalog(threadId: string): Promise<ToolCatalogDTO> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/threads/${encodeURIComponent(threadId)}/tools/`);
  }

  preferences(threadId: string): Promise<ThreadPreferencesDTO> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/threads/${encodeURIComponent(threadId)}/preferences/`);
  }

  /**
   * Persist the enabled tool allowlist. The server requires the preferences
   * revision for optimistic locking (If-Match); a mismatch raises a
   * `chat_preferences_revision_conflict` business error the caller should
   * handle by refetching the catalog and retrying once.
   */
  updateEnabledTools(threadId: string, enabledTools: string[], revision: number): Promise<ThreadPreferencesDTO> {
    const payload: ThreadPreferencesUpdateDTO & { revision?: number } = { enabled_tools: enabledTools };
    return this.http.requestOrThrow("PATCH", `/api/v1/ai/chat/threads/${encodeURIComponent(threadId)}/preferences/`, {
      body: payload,
      headers: { "If-Match": `"${revision}"` },
    });
  }
}
