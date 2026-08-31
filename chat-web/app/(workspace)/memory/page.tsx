"use client";

import { useEffect, useMemo, useState } from "react";
import { Brain, Plus, RefreshCw } from "lucide-react";
import { useOptionalAuth } from "@/context/AuthContext";
import { SparkMemoryApi } from "@/lib/api/memory-api";
import { MemoryEntryEditor } from "@/components/memory/MemoryEntryEditor";
import { MemoryEntryList } from "@/components/memory/MemoryEntryList";
import type { MemoryEntryDTO } from "@/types/memory";

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `memory-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function MemoryPage() {
  const auth = useOptionalAuth();
  const api = useMemo(() => (auth ? new SparkMemoryApi(auth.client) : null), [auth]);
  const [items, setItems] = useState<MemoryEntryDTO[] | null>(null);
  const [selected, setSelected] = useState<MemoryEntryDTO | null>(null);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const load = async () => {
    if (!api) return;
    setError(null);
    try {
      const data = await api.listEntries();
      setItems(data.items);
      setSelected((current) => (current ? data.items.find((item) => item.id === current.id) ?? null : null));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "记忆列表加载失败");
      setItems([]);
    }
  };

  useEffect(() => { void load(); }, [api]);

  const create = async (draft: { title: string; content: string }) => {
    if (!api) return;
    const content = draft.content.trim();
    if (!content) {
      setCreateError("请填写记忆内容");
      return;
    }
    setSaving(true);
    setCreateError(null);
    try {
      const created = await api.createPreference(
        { title: draft.title.trim() || undefined, content },
        newIdempotencyKey(),
      );
      setCreating(false);
      await load();
      setSelected(created);
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : "创建失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="knowledge-page">
      <header className="knowledge-page__header">
        <div>
          <p className="feature-page__eyebrow">MEMORY</p>
          <h1>记忆</h1>
          <p>查看已保存的记忆，或新建一条。记忆创建后不可编辑或删除。</p>
        </div>
        <div className="knowledge-page__actions">
          <button type="button" className="secondary" onClick={() => void load()} aria-label="刷新"><RefreshCw size={15} /></button>
          <button type="button" onClick={() => { setCreateError(null); setCreating(true); }}><Plus size={15} />新建记忆</button>
        </div>
      </header>
      {items === null && <div className="knowledge-skeleton" aria-hidden="true">{Array.from({ length: 3 }).map((_, index) => <div key={index} className="knowledge-card knowledge-card--skeleton" />)}</div>}
      {error && <div className="knowledge-banner" role="alert"><span>{error}</span><button type="button" onClick={() => void load()}>重试</button></div>}
      {items && items.length === 0 && !error && (
        <div className="knowledge-empty">
          <Brain size={22} />
          <h2>还没有记忆</h2>
          <p>把长期回答偏好保存下来，对话时可以由 AI 读取。</p>
          <button type="button" onClick={() => setCreating(true)}>立即创建</button>
        </div>
      )}
      {items && items.length > 0 && (
        <div className="memory-workspace">
          <MemoryEntryList items={items} empty="还没有记忆" onSelect={setSelected} />
          {selected && (
            <article className="knowledge-card">
              <h2>{selected.title || "未命名记忆"}</h2>
              <p>{selected.content}</p>
            </article>
          )}
        </div>
      )}
      {creating && (
        <MemoryEntryEditor
          onCancel={() => { setCreating(false); setCreateError(null); }}
          onSave={(draft) => void create(draft)}
          saving={saving}
          error={createError}
        />
      )}
    </section>
  );
}
