"use client";

import { BookMarked } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useOptionalAuth } from "@/context/AuthContext";
import { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import type { KnowledgeBaseSummary } from "@/types/knowledge";

const INDEX_HINT: Record<string, string> = {
  pending: "暂不可检索",
  processing: "正在建立索引",
  ready: "可用于对话",
  failed: "索引失败",
  stale: "索引待更新",
};

export function KnowledgeSelector({
  selectedIds,
  onChange,
}: {
  selectedIds: string[];
  onChange: (ids: string[]) => Promise<boolean> | boolean;
}) {
  const auth = useOptionalAuth();
  const api = useMemo(() => (auth ? new SparkKnowledgeApi(auth.client) : null), [auth]);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<KnowledgeBaseSummary[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!api) return;
    void api.listBases({ q: query }).then((data) => setItems(data.items)).catch(() => setItems([]));
  }, [api, query, open]);

  const selected = items.filter((item) => selectedIds.includes(item.id));
  const chips = selected.slice(0, 2);
  const extra = Math.max(0, selectedIds.length - chips.length);

  const toggle = async (item: KnowledgeBaseSummary) => {
    if (item.index_status !== "ready") return;
    const next = selectedIds.includes(item.id) ? selectedIds.filter((id) => id !== item.id) : [...selectedIds, item.id];
    await onChange(next);
  };

  return (
    <div className="knowledge-selector">
      <div className="context-section-title"><BookMarked size={15} /><strong>知识库</strong></div>
      <button className="context-trigger" type="button" onClick={() => setOpen((value) => !value)}>
        <span>{selectedIds.length ? `${selectedIds.length} 个知识库` : "未选择知识库"}</span>
      </button>
      {chips.map((item) => <span key={item.id} className="context-chip">{item.name}</span>)}
      {extra > 0 && <span className="context-count">+{extra}</span>}
      {open && (
        <div className="knowledge-selector__menu">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索知识库" aria-label="搜索知识库" />
          {items.map((item) => {
            const disabled = item.index_status !== "ready";
            const checked = selectedIds.includes(item.id);
            return (
              <label key={item.id} className={disabled ? "is-disabled" : undefined}>
                <input type="checkbox" checked={checked} disabled={disabled} onChange={() => void toggle(item)} />
                <span>{item.name}</span>
                <em>{INDEX_HINT[item.index_status]}</em>
              </label>
            );
          })}
          {items.length === 0 && <p>没有可访问的知识库</p>}
        </div>
      )}
    </div>
  );
}
