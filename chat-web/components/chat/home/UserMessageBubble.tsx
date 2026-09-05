"use client";

import { blockAssociatedValue } from "@/lib/chat/block-normalizer";
import { renderBlock } from "@/components/chat/blocks/registry";
import type { ChatBlockDTO } from "@/types/chat";

/**
 * 用户/患者消息内容（CHAT-WEB-029）：text block 以纯文本渲染（不套 Markdown），
 * imageGallery block 复用 registry 的图片渲染，其余忽略。
 * 主 chat 用户气泡与医生工作台患者消息共用同一套渲染，保证跨端图片语义一致。
 */
export function UserMessageContent({ blocks }: { blocks: ChatBlockDTO[] }) {
  const text = blocks.map((block) => {
    const value = blockAssociatedValue(block);
    return typeof value === "string" ? value : "";
  }).filter(Boolean).join("\n\n");
  const galleries = blocks.filter((block) => block.kind === "imageGallery");
  return <>
    {galleries.map((block, index) => <div className="message__gallery" key={block.id || index}>{renderBlock({ block })}</div>)}
    {text || galleries.length === 0 ? <div className="message__body">{text}</div> : null}
  </>;
}
