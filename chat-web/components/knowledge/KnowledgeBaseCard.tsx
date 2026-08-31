"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { MoreHorizontal } from "lucide-react";
import { useState } from "react";
import { useOptionalAuth } from "@/context/AuthContext";
import { SparkKnowledgeApi } from "@/lib/api/knowledge-api";
import type { KnowledgeBaseSummary } from "@/types/knowledge";

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
        <p>{item.document_count} 篇文档</p>
        <div className="knowledge-card__meta">
          <span className="knowledge-sync">{item.sync_status === "synced" ? "已同步" : "等待同步"}</span>
          <time>{updated}</time>
        </div>
      </Link>
      <button className="knowledge-card__more" type="button" aria-label="知识库操作" onClick={() => setMenu((value) => !value)}><MoreHorizontal size={16} /></button>
      {menu && auth && (
        <div className="knowledge-menu" role="menu">
          <button type="button" onClick={() => { setMenu(false); router.push(`/knowledge/${item.id}?tab=settings` as never); }}>重命名</button>
          {!item.is_default && <button type="button" onClick={async () => { await new SparkKnowledgeApi(auth.client).updateBase(item.id, item.revision, { make_default: true }); setMenu(false); onChanged(); }}>设为默认</button>}
          {item.is_default ? null : <button type="button" className="danger" onClick={async () => { if (!confirm("确定删除该知识库？文档将一并标记为删除。")) return; await new SparkKnowledgeApi(auth.client).deleteBase(item.id, item.revision); setMenu(false); onChanged(); }}>删除</button>}
        </div>
      )}
    </article>
  );
}
