"use client";

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatBlockDTO } from "@/types/chat";
import { useSmoothStreamText } from "@/hooks/useSmoothStreamText";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { CHAT_SMOOTH_STREAM_ENABLED } from "@/lib/feature-flags";

const MARKDOWN_LINK_COMPONENTS = {
  a: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a {...props} target="_blank" rel="noreferrer noopener">{children}</a>
  ),
};

interface AssistantResponseProps {
  block: ChatBlockDTO;
  text: string;
}

/**
 * CHAT-WEB-027 W2: unified entry point for rendering a streaming/completed
 * assistant text Block with frame-rate-smooth reveal.
 *
 * Only ever receives the Canonical `ChatBlockDTO` (+ its already-decoded
 * text) — never a DeepTutor Message/StreamEvent/UnifiedChatContext. Smooth
 * reveal is purely a client-side paint-speed concern layered on top of text
 * the reducer already holds in full; it never affects the canonical model,
 * run state or message sync.
 */
function AssistantResponseImpl({ block, text }: AssistantResponseProps) {
  const reducedMotion = usePrefersReducedMotion();
  const isStreaming = block.status === "streaming";
  const smoothingEnabled = CHAT_SMOOTH_STREAM_ENABLED && !reducedMotion;
  const displayText = useSmoothStreamText(text, isStreaming, { enabled: smoothingEnabled });

  if (!displayText) return null;
  return (
    <div className="block markdown-body" aria-live="polite" aria-atomic="false">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_LINK_COMPONENTS}>{displayText}</ReactMarkdown>
      {isStreaming && <span className="streaming-cursor" aria-label="内容生成中" />}
    </div>
  );
}

/** Skip re-render when nothing about this block's identity/content changed,
 * even if the parent list re-rendered for an unrelated sibling block/turn. */
function areEqual(prev: AssistantResponseProps, next: AssistantResponseProps): boolean {
  return (
    prev.block.id === next.block.id &&
    prev.block.status === next.block.status &&
    prev.block.revision === next.block.revision &&
    prev.text === next.text
  );
}

export const AssistantResponse = memo(AssistantResponseImpl, areEqual);
