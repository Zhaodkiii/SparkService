"use client";

import { useEffect, useState } from "react";
import type { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import { KnowledgeDocumentEditor } from "@/components/knowledge/KnowledgeDocumentEditor";
import type { KnowledgeDocumentDTO } from "@/types/knowledge";

export function KnowledgeDocumentList({ api, baseId }: { api: SparkKnowledgeApi; baseId: string }) {
  const [items, setItems] = useState<KnowledgeDocumentDTO[]>([]);
  const [editing, setEditing] = useState<KnowledgeDocumentDTO | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const data = await api.listDocuments(baseId);
      setItems(data.items);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "文档列表加载失败");
    }
  };

  useEffect(() => { void load(); }, [api, baseId]);

  if (editing) {
    return <KnowledgeDocumentEditor api={api} baseId={baseId} document={editing === "new" ? null : editing} onClose={() => { setEditing(null); void load(); }} />;
  }

  return (
    <div className="knowledge-list">
      <div className="knowledge-page__actions"><button type="button" onClick={() => setEditing("new")}>新建文档</button></div>
      {error && <p className="knowledge-error">{error}</p>}
      {items.length === 0 && <p className="knowledge-empty-copy">还没有文档。可以手工撰写，或从文件页导入。</p>}
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <button type="button" onClick={async () => { const full = await api.getDocument(item.id); setEditing(full); }}>
              <strong>{item.title}</strong>
              <span>{item.excerpt || "无摘要"}</span>
              <em>{item.index_state.status}</em>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
