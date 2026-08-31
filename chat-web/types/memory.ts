export interface MemoryEntryDTO {
  id: string;
  title: string;
  content: string;
  section_key: string;
  memory_type: string;
  revision: number;
  status: string;
  is_pinned: boolean;
  is_deleted: boolean;
  source: string;
  created_at: string | null;
  server_updated_at: string | null;
}

export interface MemoryCreatePayload {
  title?: string;
  content: string;
  section_key?: string;
}

export interface MemoryEntryPage {
  items: MemoryEntryDTO[];
  next_cursor: string | null;
  has_more?: boolean;
}
