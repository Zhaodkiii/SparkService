"use client";

import { useEffect, useState } from "react";
import type { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import type { KnowledgeIndexVersionDTO } from "@/types/knowledge";

export function KnowledgeIndexVersionsSection({ api, baseId }: { api: SparkKnowledgeApi; baseId: string }) {
  const [items, setItems] = useState<KnowledgeIndexVersionDTO[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setItems((await api.listIndexVersions(baseId)).items);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "索引版本加载失败");
    }
  };

  useEffect(() => { void load(); }, [api, baseId]);

  return (
    <div className="knowledge-list">
      <div className="knowledge-page__actions"><button type="button" onClick={async () => { await api.rebuildIndex(baseId); await load(); }}>重建索引</button></div>
      {error && <p className="knowledge-error">{error}</p>}
      {items.length === 0 && <p className="knowledge-empty-copy">还没有索引版本。添加文档后会自动开始建立。</p>}
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <strong>{item.signature || item.id.slice(0, 8)}</strong>
            <span>{item.status}{item.is_active ? " · 当前" : ""}</span>
            <span>{item.document_count} 篇 / {item.chunk_count} 片段</span>
            {item.error_message && <em>{item.error_message}</em>}
          </li>
        ))}
      </ul>
    </div>
  );
}
