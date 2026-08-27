"use client";

import { useEffect, useRef, useState } from "react";
import { BrainCircuit, ChevronDown, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatBlockDTO } from "@/types/chat";
import { asString, blockValueObject, blockValue } from "@/components/chat/blocks/common";

function extractPublicSummary(block: ChatBlockDTO): string {
  const value = blockValue(block);
  if (typeof value === "string") return value;
  const object = blockValueObject(block);
  return asString(object.summary) ?? asString(object.reasoning_content) ?? asString(object.text) ?? asString(object.content) ?? "";
}

/**
 * DeepTutor-aligned collapsible shell. Expanded while the block is still
 * streaming, auto-collapses once it settles, and a manual toggle pins the
 * user's preference for the rest of the block's lifetime.
 */
function ThinkingCard({ block, title, summary }: { block: ChatBlockDTO; title: string; summary: string }) {
  const isStreaming = block.status === "streaming";
  const [userToggled, setUserToggled] = useState<boolean | null>(null);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const open = userToggled !== null ? userToggled : isStreaming;

  useEffect(() => {
    const el = detailsRef.current;
    if (el && el.open !== open) el.open = open;
  }, [open]);

  const handleToggle = (event: React.SyntheticEvent<HTMLDetailsElement>) => {
    const next = event.currentTarget.open;
    if (next !== open) setUserToggled(next);
  };

  return <details ref={detailsRef} onToggle={handleToggle} className="public-thinking public-thinking--details">
    <summary className="public-thinking__summary">
      <ChevronDown size={12} className="public-thinking__chevron" aria-hidden="true" />
      <BrainCircuit size={12} aria-hidden="true" />
      <span>{title}</span>
      {isStreaming && <Loader2 size={11} className="public-thinking__spin" aria-hidden="true" />}
    </summary>
    <div className="public-thinking__body markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{summary}</ReactMarkdown></div>
  </details>;
}

/** 公开思考摘要卡：只在展开的 Activity 折叠体内展示模型公开的思考摘要。 */
export function PublicThinkingCard({ block }: { block: ChatBlockDTO }) {
  const title = asString(blockValueObject(block).title) ?? "思考";
  const summary = extractPublicSummary(block);
  if (!summary) return null;
  return <ThinkingCard block={block} title={title} summary={summary} />;
}
