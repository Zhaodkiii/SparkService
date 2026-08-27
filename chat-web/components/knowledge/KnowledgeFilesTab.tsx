"use client";

import { useEffect, useState } from "react";
import type { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import type { KnowledgeFileDTO } from "@/types/knowledge";

export function KnowledgeFilesTab({ api, baseId }: { api: SparkKnowledgeApi; baseId: string }) {
  const [items, setItems] = useState<KnowledgeFileDTO[]>([]);
  const [fileUuid, setFileUuid] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setItems((await api.listFiles(baseId)).items);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "文件列表加载失败");
    }
  };

  useEffect(() => { void load(); }, [api, baseId]);

  return (
    <div className="knowledge-list">
      <p className="knowledge-empty-copy">先通过文件服务上传，再粘贴 ManagedFile UUID 绑定到本知识库。上传成功不等于可检索。</p>
      <div className="context-inline">
        <input value={fileUuid} onChange={(event) => setFileUuid(event.target.value)} placeholder="file_uuid" />
        <button type="button" onClick={async () => { try { await api.bindFile(baseId, fileUuid.trim()); setFileUuid(""); await load(); } catch (cause) { setError(cause instanceof Error ? cause.message : "绑定失败"); } }}>绑定文件</button>
      </div>
      {error && <p className="knowledge-error">{error}</p>}
      {items.length === 0 && <p className="knowledge-empty-copy">还没有绑定文件。</p>}
      <ul>
        {items.map((item) => (
          <li key={item.file_uuid}>
            <strong>{item.name}</strong>
            <span>{item.processing_status}</span>
            {item.preview_url && <a href={item.preview_url} target="_blank" rel="noreferrer">预览</a>}
            <button type="button" className="danger" onClick={async () => { await api.unbindFile(baseId, item.file_uuid); await load(); }}>删除</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
