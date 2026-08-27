"use client";

import { useState } from "react";
import type { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import type { KnowledgeDocumentDTO } from "@/types/knowledge";

export function KnowledgeDocumentEditor({
  api,
  baseId,
  document,
  onClose,
}: {
  api: SparkKnowledgeApi;
  baseId: string;
  document: KnowledgeDocumentDTO | null;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(document?.title ?? "");
  const [content, setContent] = useState(document?.content ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true); setError(null);
    try {
      if (document) {
        await api.updateDocument(document.id, document.revision, { title, content });
      } else {
        await api.createDocument(baseId, { title, content });
      }
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败，可能已被其他设备更新，请刷新后再编辑。");
      setBusy(false);
    }
  };

  return (
    <div className="knowledge-editor">
      <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="标题" />
      <textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="正文" rows={16} />
      {error && <p className="knowledge-error">{error}</p>}
      <footer>
        <button type="button" className="secondary" onClick={onClose}>取消</button>
        {document && <button type="button" className="danger" onClick={async () => { if (confirm("确定删除该文档？")) { await api.deleteDocument(document.id, document.revision); onClose(); } }}>删除</button>}
        <button type="button" onClick={() => void save()} disabled={busy}>保存</button>
      </footer>
    </div>
  );
}
