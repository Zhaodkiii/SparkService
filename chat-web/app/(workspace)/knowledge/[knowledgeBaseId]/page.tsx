"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useOptionalAuth } from "@/context/AuthContext";
import { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import { KnowledgeDocumentList } from "@/components/knowledge/KnowledgeDocumentList";
import { KnowledgeFilesTab } from "@/components/knowledge/KnowledgeFilesTab";
import { KnowledgeIndexVersionsSection } from "@/components/knowledge/KnowledgeIndexVersionsSection";
import { KnowledgeSettingsSection } from "@/components/knowledge/KnowledgeSettingsSection";
import type { KnowledgeBaseDetail } from "@/types/knowledge";

const TABS = [
  { id: "overview", label: "概览" },
  { id: "documents", label: "文档" },
  { id: "files", label: "文件" },
  { id: "index", label: "索引版本" },
  { id: "settings", label: "设置" },
] as const;

export default function KnowledgeBaseDetailPage() {
  const params = useParams<{ knowledgeBaseId: string }>();
  const search = useSearchParams();
  const auth = useOptionalAuth();
  const api = useMemo(() => (auth ? new SparkKnowledgeApi(auth.client) : null), [auth]);
  const [detail, setDetail] = useState<KnowledgeBaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>((search.get("tab") as (typeof TABS)[number]["id"]) || "overview");

  const load = async () => {
    if (!api) return;
    try {
      setDetail(await api.getBase(params.knowledgeBaseId));
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法加载知识库");
    }
  };

  useEffect(() => { void load(); }, [api, params.knowledgeBaseId]);

  if (error) return <section className="knowledge-page"><p>{error}</p><Link href="/knowledge">返回列表</Link></section>;
  if (!detail || !api) return <section className="knowledge-page"><div className="knowledge-skeleton" /></section>;

  return (
    <section className="knowledge-page knowledge-page--detail">
      <Link href="/knowledge" className="knowledge-back"><ArrowLeft size={14} />知识中心</Link>
      <header className="knowledge-page__header">
        <div>
          <h1>{detail.name}</h1>
          <p>{detail.document_count} 篇文档 · {detail.file_count} 个文件 · 索引 {detail.index_status}</p>
        </div>
      </header>
      <nav className="knowledge-tabs" aria-label="知识库分区">
        {TABS.map((item) => (
          <button key={item.id} type="button" aria-current={tab === item.id} onClick={() => setTab(item.id)}>{item.label}</button>
        ))}
      </nav>
      {tab === "overview" && (
        <div className="knowledge-overview">
          <article><h2>检索设置</h2><p>top_k {detail.retrieval_config.top_k} · 阈值 {detail.retrieval_config.score_threshold}</p></article>
          <article><h2>文档状态</h2><p>就绪 {detail.documents_summary.ready} · 处理中 {detail.documents_summary.pending} · 失败 {detail.documents_summary.failed}</p></article>
        </div>
      )}
      {tab === "documents" && <KnowledgeDocumentList api={api} baseId={detail.id} />}
      {tab === "files" && <KnowledgeFilesTab api={api} baseId={detail.id} />}
      {tab === "index" && <KnowledgeIndexVersionsSection api={api} baseId={detail.id} />}
      {tab === "settings" && <KnowledgeSettingsSection api={api} detail={detail} onChanged={load} />}
    </section>
  );
}
