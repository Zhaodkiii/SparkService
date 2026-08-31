export type KnowledgeSyncStatus = "synced" | "pending" | "failed" | "conflict";
export type KnowledgeBaseKind = "personal" | "shared" | "system" | "imported";

export interface KnowledgeBaseSummary {
  id: string;
  name: string;
  kind: KnowledgeBaseKind;
  is_default: boolean;
  revision: number;
  document_count: number;
  sync_status: KnowledgeSyncStatus;
  server_updated_at: string;
}

export interface KnowledgeBaseDetail extends KnowledgeBaseSummary {
  created_at: string;
  is_deleted: boolean;
  permissions: { can_edit: boolean; can_delete: boolean };
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
  content_hash: string;
  is_deleted: boolean;
  deleted_at: string | null;
  created_at: string;
  server_updated_at: string;
}

export interface CursorPage<T> {
  items: T[];
  next_cursor: string | null;
}
