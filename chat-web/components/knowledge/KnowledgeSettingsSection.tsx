"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import type { KnowledgeBaseDetail } from "@/types/knowledge";

export function KnowledgeSettingsSection({ api, detail, onChanged }: { api: SparkKnowledgeApi; detail: KnowledgeBaseDetail; onChanged: () => Promise<void> | void }) {
  const router = useRouter();
  const [name, setName] = useState(detail.name);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    try {
      await api.updateBase(detail.id, detail.revision, { name });
      setError(null);
      await onChanged();
    } catch {
      setError("已采用服务器版本，请刷新后再编辑。");
    }
  };

  return (
    <div className="knowledge-editor">
      <label>名称<input value={name} onChange={(event) => setName(event.target.value)} /></label>
      {error && <p className="knowledge-error">{error}</p>}
      <footer>
        <button type="button" onClick={() => void save()}>保存设置</button>
        {detail.permissions.can_delete && (
          <button type="button" className="danger" onClick={async () => {
            if (!confirm("确定删除该知识库？文档将一并标记为删除。")) return;
            await api.deleteBase(detail.id, detail.revision);
            router.push("/knowledge");
          }}>删除知识库</button>
        )}
      </footer>
    </div>
  );
}
