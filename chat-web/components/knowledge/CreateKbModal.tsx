"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { X } from "lucide-react";
import type { SparkKnowledgeApi } from "@/lib/api/knowledge-api";

export function CreateKbModal({ api, onClose }: { api: SparkKnowledgeApi; onClose: () => void }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [makeDefault, setMakeDefault] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const title = name.trim();
    if (!title) { setError("请输入知识库名称"); return; }
    setBusy(true); setError(null);
    try {
      const created = await api.createBase({ name: title, make_default: makeDefault }, crypto.randomUUID());
      onClose();
      router.push(`/knowledge/${created.id}` as never);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建失败");
      setBusy(false);
    }
  };

  return (
    <div className="knowledge-modal" role="dialog" aria-labelledby="create-kb-title">
      <div className="knowledge-modal__card">
        <header>
          <h2 id="create-kb-title">新建知识库</h2>
          <button type="button" aria-label="关闭" onClick={onClose}><X size={16} /></button>
        </header>
        <label>名称<input value={name} onChange={(event) => setName(event.target.value)} maxLength={128} placeholder="例如：糖尿病随访资料" /></label>
        <label className="knowledge-check"><input type="checkbox" checked={makeDefault} onChange={(event) => setMakeDefault(event.target.checked)} />设为默认个人库</label>
        {error && <p className="knowledge-error">{error}</p>}
        <footer>
          <button type="button" className="secondary" onClick={onClose}>取消</button>
          <button type="button" onClick={() => void submit()} disabled={busy}>{busy ? "创建中…" : "创建"}</button>
        </footer>
      </div>
    </div>
  );
}
