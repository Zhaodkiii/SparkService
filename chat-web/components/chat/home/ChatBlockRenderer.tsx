"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatBlockDTO } from "@/types/chat";

export function ChatBlockRenderer({ block }: { block: ChatBlockDTO }) {
  const fallback = typeof block.payload.fallback_text === "string" ? block.payload.fallback_text : "此内容需要更新版本查看";
  if (block.kind !== "text") return <div className="block block--unknown" role="status"><strong>结构化内容</strong><p>{fallback}</p></div>;
  const text = typeof block.payload.text === "string" ? block.payload.text : fallback;
  return <div className="block markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer noopener">{children}</a> }}>{text}</ReactMarkdown>{block.status === "streaming" && <span className="streaming-cursor" aria-label="内容生成中" />}</div>;
}
