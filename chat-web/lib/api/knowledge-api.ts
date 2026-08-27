import type { SparkHttpClient } from "@/lib/api/http-client";
import type {
  CursorPage,
  KnowledgeBaseDetail,
  KnowledgeBaseSummary,
  KnowledgeDocumentDTO,
  KnowledgeFileDTO,
  KnowledgeIndexVersionDTO,
  KnowledgeRetrievalConfig,
} from "@/types/knowledge";

function segment(value: string): string {
  return encodeURIComponent(value);
}

export class SparkKnowledgeApi {
  constructor(private readonly http: SparkHttpClient) {}

  listBases(query?: { cursor?: string; q?: string; index_status?: string }): Promise<CursorPage<KnowledgeBaseSummary>> {
    const params = new URLSearchParams();
    if (query?.cursor) params.set("cursor", query.cursor);
    if (query?.q) params.set("q", query.q);
    if (query?.index_status) params.set("index_status", query.index_status);
    const suffix = params.toString() ? `?${params}` : "";
    return this.http.requestOrThrow("GET", `/api/v1/ai/knowledge/bases/${suffix}`);
  }

  createBase(body: { name: string; make_default?: boolean; retrieval_config?: Partial<KnowledgeRetrievalConfig> }, idempotencyKey: string): Promise<KnowledgeBaseDetail> {
    return this.http.requestOrThrow("POST", "/api/v1/ai/knowledge/bases/", {
      body,
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }

  getBase(id: string): Promise<KnowledgeBaseDetail> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/knowledge/bases/${segment(id)}/`);
  }

  updateBase(id: string, revision: number, patch: { name?: string; make_default?: boolean; retrieval_config?: Partial<KnowledgeRetrievalConfig> }): Promise<KnowledgeBaseDetail> {
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

  listDocuments(baseId: string, cursor?: string): Promise<CursorPage<KnowledgeDocumentDTO>> {
    const suffix = cursor ? `?cursor=${segment(cursor)}` : "";
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

  listFiles(baseId: string): Promise<{ items: KnowledgeFileDTO[] }> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/knowledge/bases/${segment(baseId)}/files/`);
  }

  bindFile(baseId: string, fileUuid: string, reuse = false): Promise<{ document_id: string; reused: boolean }> {
    return this.http.requestOrThrow("POST", `/api/v1/ai/knowledge/bases/${segment(baseId)}/files/`, {
      body: { file_uuid: fileUuid, reuse },
    });
  }

  unbindFile(baseId: string, fileUuid: string): Promise<{ unbound: boolean }> {
    return this.http.requestOrThrow("DELETE", `/api/v1/ai/knowledge/bases/${segment(baseId)}/files/${segment(fileUuid)}/`);
  }

  listIndexVersions(baseId: string): Promise<{ items: KnowledgeIndexVersionDTO[] }> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/knowledge/bases/${segment(baseId)}/index-versions/`);
  }

  rebuildIndex(baseId: string): Promise<{ job_id: string; status: string }> {
    return this.http.requestOrThrow("POST", `/api/v1/ai/knowledge/bases/${segment(baseId)}/index-jobs/`, { body: {} });
  }
}
