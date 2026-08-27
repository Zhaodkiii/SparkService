export type KnowledgeIndexStatus = "pending" | "processing" | "ready" | "failed" | "stale";
export type KnowledgeSyncStatus = "synced" | "pending" | "failed" | "conflict";
export type KnowledgeBaseKind = "personal" | "shared" | "system" | "imported";

export interface KnowledgeRetrievalConfig {
  top_k: number;
  score_threshold: number;
  rerank_enabled: boolean;
}

export interface KnowledgeIndexStateDTO {
  status: KnowledgeIndexStatus;
  indexed_revision: number;
  chunk_count: number;
  index_version: string | null;
  error_code: string | null;
  error_message: string;
  indexed_at: string | null;
}

export interface KnowledgeBaseSummary {
  id: string;
  name: string;
  kind: KnowledgeBaseKind;
  is_default: boolean;
  revision: number;
  document_count: number;
  file_count: number;
  index_status: KnowledgeIndexStatus;
  active_index_version: string | null;
  sync_status: KnowledgeSyncStatus;
  server_updated_at: string;
}

export interface KnowledgeBaseDetail extends KnowledgeBaseSummary {
  created_at: string;
  is_deleted: boolean;
  retrieval_config: KnowledgeRetrievalConfig;
  documents_summary: { ready: number; pending: number; failed: number };
  latest_index: KnowledgeIndexVersionDTO | null;
  permissions: { can_edit: boolean; can_delete: boolean; can_reindex: boolean };
}

export interface KnowledgeSourceFile {
  file_uuid: string;
  name: string;
  mime_type: string;
  size: number;
  preview_url: string | null;
}

export interface KnowledgeDocumentDTO {
  id: string;
  knowledge_base_id: string;
  revision: number;
  title: string;
  excerpt: string;
  content?: string;
  source: string;
  scope: string;
  bound_model_id: string | null;
  source_file: KnowledgeSourceFile | null;
  content_hash: string;
  is_deleted: boolean;
  deleted_at: string | null;
  index_state: KnowledgeIndexStateDTO;
  created_at: string;
  server_updated_at: string;
}

export interface KnowledgeFileDTO {
  file_uuid: string;
  name: string;
  mime_type: string;
  size: number;
  preview_url: string | null;
  document_id: string | null;
  processing_status: string;
  error_code: string | null;
}

export interface KnowledgeIndexVersionDTO {
  id: string;
  knowledge_base_id: string;
  status: KnowledgeIndexStatus;
  is_active: boolean;
  signature: string | null;
  document_count: number;
  chunk_count: number;
  embedding_provider: string | null;
  embedding_model: string | null;
  dimension: number | null;
  chunker_version: string;
  started_at: string | null;
  completed_at: string | null;
  error_code: string | null;
  error_message: string;
}

export interface KnowledgeCitationDTO {
  citation_id: string;
  knowledge_base_id: string;
  knowledge_base_name: string;
  document_id: string;
  document_title: string;
  chunk_id: string;
  chunk_revision: number;
  index_version: string | null;
  snippet: string;
  relevance: "high" | "medium" | "low";
}

export interface CursorPage<T> {
  items: T[];
  next_cursor: string | null;
}
