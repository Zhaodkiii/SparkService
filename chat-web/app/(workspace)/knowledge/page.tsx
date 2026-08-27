"use client";

import { useEffect, useMemo, useState } from "react";
import { BookOpen, Plus, RefreshCw } from "lucide-react";
import { useOptionalAuth } from "@/context/AuthContext";
import { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import { KnowledgeBaseCard } from "@/components/knowledge/KnowledgeBaseCard";
import { CreateKbModal } from "@/components/knowledge/CreateKbModal";
import type { KnowledgeBaseSummary } from "@/types/knowledge";

export default function KnowledgePage() {
  const auth = useOptionalAuth();
  const api = useMemo(() => (auth ? new SparkKnowledgeApi(auth.client) : null), [auth]);
  const [items, setItems] = useState<KnowledgeBaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = async () => {
    if (!api) return;
    setError(null);
    try {
      const data = await api.listBases();
      setItems(data.items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "知识库列表加载失败");
      setItems([]);
    }
  };

  useEffect(() => { void load(); }, [api]);

  return (
    <section className="knowledge-page">
      <header className="knowledge-page__header">
        <div>
          <p className="feature-page__eyebrow">KNOWLEDGE</p>
          <h1>知识中心</h1>
          <p>管理可在对话中引用的资料库。同步与索引都在后台进行，不会打断聊天。</p>
        </div>
        <div className="knowledge-page__actions">
          <button type="button" className="secondary" onClick={() => void load()} aria-label="刷新"><RefreshCw size={15} /></button>
          <button type="button" onClick={() => setCreating(true)}><Plus size={15} />新建知识库</button>
        </div>
      </header>
      {items === null && <div className="knowledge-skeleton" aria-hidden="true">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="knowledge-card knowledge-card--skeleton" />)}</div>}
      {error && <div className="knowledge-banner" role="alert"><span>{error}</span><button type="button" onClick={() => void load()}>重试</button></div>}
      {items && items.length === 0 && !error && (
        <div className="knowledge-empty">
          <BookOpen size={22} />
          <h2>创建第一个知识库</h2>
          <p>把随访资料、指南摘要放进知识库，对话时即可检索引用。</p>
          <button type="button" onClick={() => setCreating(true)}>立即创建</button>
        </div>
      )}
      {items && items.length > 0 && <div className="knowledge-grid">{items.map((item) => <KnowledgeBaseCard key={item.id} item={item} onChanged={() => void load()} />)}</div>}
      {creating && api && <CreateKbModal api={api} onClose={() => setCreating(false)} />}
    </section>
  );
}
