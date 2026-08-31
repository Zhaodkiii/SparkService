import type { SparkHttpClient } from "@/lib/api/http-client";
import type {
  CursorPage,
  KnowledgeBaseDetail,
  KnowledgeBaseSummary,
  KnowledgeDocumentDTO,
} from "@/types/knowledge";

function segment(value: string): string {
  return encodeURIComponent(value);
}

export class SparkKnowledgeApi {
  constructor(private readonly http: SparkHttpClient) {}

  listBases(query?: { cursor?: string; q?: string }): Promise<CursorPage<KnowledgeBaseSummary>> {
    const params = new URLSearchParams();
    if (query?.cursor) params.set("cursor", query.cursor);
    if (query?.q) params.set("q", query.q);
    const suffix = params.toString() ? `?${params}` : "";
    return this.http.requestOrThrow("GET", `/api/v1/ai/knowledge/bases/${suffix}`);
  }

  createBase(body: { name: string; make_default?: boolean }, idempotencyKey: string): Promise<KnowledgeBaseDetail> {
    return this.http.requestOrThrow("POST", "/api/v1/ai/knowledge/bases/", {
      body,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }

  getBase(id: string): Promise<KnowledgeBaseDetail> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/knowledge/bases/${segment(id)}/`);
  }

  updateBase(id: string, revision: number, patch: { name?: string; make_default?: boolean }): Promise<KnowledgeBaseDetail> {
    return this.http.requestOrThrow("PATCH", `/api/v1/ai/knowledge/bases/${segment(id)}/`, {
      body: patch,
      headers: { "If-Match": `"${revision}"` },
    });
  }

  deleteBase(id: string, revision: number): Promise<{ id: string; is_deleted: boolean }> {
    return this.http.requestOrThrow("DELETE", `/api/v1/ai/knowledge/bases/${segment(id)}/`, {
      headers: { "If-Match": `"${revision}"` },
    });
  }

  listDocuments(baseId: string, query?: { cursor?: string; q?: string }): Promise<CursorPage<KnowledgeDocumentDTO>> {
    const params = new URLSearchParams();
    if (query?.cursor) params.set("cursor", query.cursor);
    if (query?.q) params.set("q", query.q);
    const suffix = params.toString() ? `?${params}` : "";
    return this.http.requestOrThrow("GET", `/api/v1/ai/knowledge/bases/${segment(baseId)}/documents/${suffix}`);
  }

  createDocument(baseId: string, body: { title: string; content: string }): Promise<KnowledgeDocumentDTO> {
    return this.http.requestOrThrow("POST", `/api/v1/ai/knowledge/bases/${segment(baseId)}/documents/`, { body });
  }

  getDocument(id: string): Promise<KnowledgeDocumentDTO> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/knowledge/documents/${segment(id)}/`);
  }

  updateDocument(id: string, revision: number, body: { title?: string; content?: string }): Promise<KnowledgeDocumentDTO> {
    return this.http.requestOrThrow("PATCH", `/api/v1/ai/knowledge/documents/${segment(id)}/`, {
      body,
      headers: { "If-Match": `"${revision}"` },
    });
  }

  deleteDocument(id: string, revision: number): Promise<{ id: string; is_deleted: boolean }> {
    return this.http.requestOrThrow("DELETE", `/api/v1/ai/knowledge/documents/${segment(id)}/`, {
      headers: { "If-Match": `"${revision}"` },
    });
  }
}
