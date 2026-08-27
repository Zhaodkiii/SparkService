"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { MoreHorizontal } from "lucide-react";
import { useState } from "react";
import { useOptionalAuth } from "@/context/AuthContext";
import { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import type { KnowledgeBaseSummary } from "@/types/knowledge";

const INDEX_LABEL: Record<string, string> = {
  pending: "等待索引",
  processing: "正在建立索引",
  ready: "可用于对话",
  failed: "索引失败",
  stale: "索引待更新",
};

export function KnowledgeBaseCard({ item, onChanged }: { item: KnowledgeBaseSummary; onChanged: () => void }) {
  const router = useRouter();
  const auth = useOptionalAuth();
  const [menu, setMenu] = useState(false);
  const updated = item.server_updated_at ? new Date(item.server_updated_at).toLocaleString("zh-CN") : "";
  return (
    <article className="knowledge-card">
      <Link href={`/knowledge/${item.id}` as never} className="knowledge-card__body">
        <header>
          <h2>{item.name}</h2>
          {item.is_default && <span className="knowledge-badge">默认</span>}
        </header>
        <p>{item.document_count} 篇文档 · {item.file_count} 个文件</p>
        <div className="knowledge-card__meta">
          <span className={`knowledge-status knowledge-status--${item.index_status}`}>{INDEX_LABEL[item.index_status] ?? item.index_status}</span>
          <span className="knowledge-sync">{item.sync_status === "synced" ? "已同步" : "等待同步"}</span>
          <time>{updated}</time>
        </div>
      </Link>
      <button className="knowledge-card__more" type="button" aria-label="知识库操作" onClick={() => setMenu((value) => !value)}><MoreHorizontal size={16} /></button>
      {menu && auth && (
        <div className="knowledge-menu" role="menu">
          <button type="button" onClick={() => { setMenu(false); router.push(`/knowledge/${item.id}?tab=settings` as never); }}>重命名</button>
          {!item.is_default && <button type="button" onClick={async () => { await new SparkKnowledgeApi(auth.client).updateBase(item.id, item.revision, { make_default: true }); setMenu(false); onChanged(); }}>设为默认</button>}
          <button type="button" onClick={async () => { await new SparkKnowledgeApi(auth.client).rebuildIndex(item.id); setMenu(false); onChanged(); }}>重建索引</button>
          {item.is_default ? null : <button type="button" className="danger" onClick={async () => { if (!confirm("立即停止被对话检索；历史对话引用不受影响。确定删除？")) return; await new SparkKnowledgeApi(auth.client).deleteBase(item.id, item.revision); setMenu(false); onChanged(); }}>删除</button>}
        </div>
      )}
    </article>
  );
}
