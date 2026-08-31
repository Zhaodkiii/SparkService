import type { SparkHttpClient } from "@/lib/api/http-client";
import type { MemoryCreatePayload, MemoryEntryDTO, MemoryEntryPage } from "@/types/memory";

function segment(value: string): string {
  return encodeURIComponent(value);
}

export class SparkMemoryApi {
  constructor(private readonly http: SparkHttpClient) {}

  listEntries(cursor?: string): Promise<MemoryEntryPage> {
    const suffix = cursor ? `?cursor=${segment(cursor)}` : "";
    return this.http.requestOrThrow("GET", `/api/v1/ai/memory/entries/${suffix}`);
  }

  getEntry(id: string): Promise<MemoryEntryDTO> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/memory/entries/${segment(id)}/`);
  }

  createPreference(body: MemoryCreatePayload, idempotencyKey: string): Promise<MemoryEntryDTO> {
    return this.http.requestOrThrow("POST", "/api/v1/ai/memory/entries/", {
      body,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }
}
