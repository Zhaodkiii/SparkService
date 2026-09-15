"use client";

import { blockAssociatedValue } from "@/lib/chat/block-normalizer";
import { renderBlock } from "@/components/chat/blocks/registry";
import type { ChatBlockDTO } from "@/types/chat";
import type { HealthResourceReference } from "@/types/medical-resource";

/**
 * 用户/患者消息内容（CHAT-WEB-029）：text block 以纯文本渲染（不套 Markdown），
 * 其余消息块统一复用 registry，保证报告引用等结构化消息不会被静默丢弃。
 * 主 chat 用户气泡与医生工作台患者消息共用同一套渲染，保证跨端消息语义一致。
 */
export function UserMessageContent({ blocks, attachmentCount, onHealthResourceOpen }: { blocks: ChatBlockDTO[]; attachmentCount?: number; onHealthResourceOpen?: (reference: HealthResourceReference) => void }) {
  const text = blocks.map((block) => {
    const value = blockAssociatedValue(block);
    return typeof value === "string" ? value : "";
  }).filter(Boolean).join("\n\n");
  const nonTextBlocks = blocks.filter((block) => block.kind !== "text");
  return <>
    {attachmentCount !== undefined ? <p className="message__attachment-label">附件（{attachmentCount}）</p> : null}
    {nonTextBlocks.map((block, index) => <div className="message__block" key={block.id || index}>{renderBlock({ block, onHealthResourceOpen })}</div>)}
    {text ? <div className="message__body">{text}</div> : null}
  </>;
}
