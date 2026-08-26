"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatBlockDTO } from "@/types/chat";
import { asString, BlockShell, blockValue, blockValueObject, ReadOnlyCard } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";
import { decodeBlockPayload } from "@/lib/chat/block-normalizer";
import { sanitizeHtml } from "@/lib/chat/sanitize-html";
import { AssistantResponse } from "@/components/chat/turn/AssistantResponse";

function extractMarkdown(block: ChatBlockDTO): string {
  const value = blockValue(block);
  if (typeof value === "string") return value;
  const record = blockValueObject(block);
  return asString(record.text) ?? asString(record.content) ?? asString(record.reasoning_content) ?? "";
}

/** Empty text is hidden, never an upgrade prompt (§6.2/§6.3). Rendering (incl.
 * smooth-stream reveal, memoization) is delegated to `AssistantResponse` so
 * there is a single source of truth for how a text Block is painted. */
export function TextBlock({ block }: BlockRenderProps) {
  const decoded = decodeBlockPayload(block.payload);
  if (decoded.status === "contract_error") return <ReadOnlyCard title="文本" subtitle="内容格式错误" />;
  const text = typeof decoded.value === "string" ? decoded.value : "";
  if (!text) return null;
  return <BlockShell block={block}><AssistantResponse block={block} text={text} /></BlockShell>;
}

export function DeepThoughtBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const title = asString(value.title) ?? "深度思考";
  const detail = asString(value.reasoning_content) ?? asString(value.content) ?? asString(value.text) ?? "";
  return <BlockShell block={block}><ReadOnlyCard title={title}>{detail ? <div className="block markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{detail}</ReactMarkdown></div> : null}</ReadOnlyCard></BlockShell>;
}

export function TranslatedTextBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const source = asString(value.source) ?? asString(value.original);
  const target = asString(value.target) ?? asString(value.translated) ?? asString(value.text);
  return <BlockShell block={block}><ReadOnlyCard title="翻译">{source ? <p className="card-row"><span className="card-row__label">原文</span><span className="card-row__value">{source}</span></p> : null}{target ? <p className="card-row"><span className="card-row__label">译文</span><span className="card-row__value">{target}</span></p> : null}</ReadOnlyCard></BlockShell>;
}

export function HtmlBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const html = asString(value.html) ?? asString(value.content) ?? asString(value.text);
  const sanitized = sanitizeHtml(html ?? "");
  if (!sanitized) return null;
  return <BlockShell block={block}><div className="block block--html" dangerouslySetInnerHTML={{ __html: sanitized }} /></BlockShell>;
}
