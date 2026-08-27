"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import type { KnowledgeBaseDetail } from "@/types/knowledge";

export function KnowledgeSettingsSection({ api, detail, onChanged }: { api: SparkKnowledgeApi; detail: KnowledgeBaseDetail; onChanged: () => Promise<void> | void }) {
  const router = useRouter();
  const [name, setName] = useState(detail.name);
  const [topK, setTopK] = useState(detail.retrieval_config.top_k);
  const [threshold, setThreshold] = useState(detail.retrieval_config.score_threshold);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    try {
      await api.updateBase(detail.id, detail.revision, { name, retrieval_config: { top_k: topK, score_threshold: threshold, rerank_enabled: detail.retrieval_config.rerank_enabled } });
      setError(null);
      await onChanged();
    } catch {
      setError("已采用服务器版本，请刷新后再编辑。");
    }
  };

  return (
    <div className="knowledge-editor">
      <label>名称<input value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label>top_k<input type="number" min={1} max={20} value={topK} onChange={(event) => setTopK(Number(event.target.value))} /></label>
      <label>score_threshold<input type="number" min={0} max={1} step={0.01} value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} /></label>
      {error && <p className="knowledge-error">{error}</p>}
      <footer>
        <button type="button" onClick={() => void save()}>保存设置</button>
        {detail.permissions.can_delete && (
          <button type="button" className="danger" onClick={async () => {
            if (!confirm("立即停止被对话检索；历史对话引用不受影响；在保留期内可恢复。确定删除？")) return;
            await api.deleteBase(detail.id, detail.revision);
            router.push("/knowledge");
          }}>删除知识库</button>
        )}
      </footer>
    </div>
  );
}
