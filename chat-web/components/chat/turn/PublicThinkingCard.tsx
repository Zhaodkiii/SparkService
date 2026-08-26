"use client";

import { useEffect, useRef, useState } from "react";
import { BrainCircuit, ChevronDown, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatBlockDTO } from "@/types/chat";
import { asString, blockValueObject, blockValue } from "@/components/chat/blocks/common";
import { CHAT_DEEPTUTOR_TURN_UI_ENABLED } from "@/lib/feature-flags";

function extractPublicSummary(block: ChatBlockDTO): string {
  // 只读取可公开的思考摘要（payload.text / summary / content），不读取隐藏推理。
  const value = blockValue(block);
  if (typeof value === "string") return value;
  const object = blockValueObject(block);
  return asString(object.summary) ?? asString(object.text) ?? asString(object.content) ?? "";
}

/**
 * DeepTutor-aligned collapsible shell (`web/components/common/ModelThinkingCard.tsx`,
 * source commit 684d615393322cd18d9edb3a85eacb3beba0d811, Apache-2.0):
 * expanded while the block is still streaming so the user watches the
 * summary arrive live, auto-collapses once it settles, and a manual toggle
 * pins the user's preference for the rest of the block's lifetime. The
 * `<details>` element is kept uncontrolled (native `open` synced imperatively
 * via ref) to avoid the React-boolean-attribute flicker DeepTutor's original
 * component documents. Input is still strictly `extractPublicSummary` — never
 * a raw `<think>` scratchpad.
 */
function DeepTutorThinkingCard({ block, title, summary }: { block: ChatBlockDTO; title: string; summary: string }) {
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

/** 公开思考摘要卡（能力二）：只在展开的 Activity 折叠体内展示模型公开的思考摘要。 */
export function PublicThinkingCard({ block }: { block: ChatBlockDTO }) {
  const title = asString(blockValueObject(block).title) ?? "思考";
  const summary = extractPublicSummary(block);
  if (!summary) return null;
  if (CHAT_DEEPTUTOR_TURN_UI_ENABLED) return <DeepTutorThinkingCard block={block} title={title} summary={summary} />;
  return <div className="public-thinking">
    <strong>{title}</strong>
    <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{summary}</ReactMarkdown></div>
  </div>;
}
