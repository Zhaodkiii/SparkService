"use client";

import { Component, type ReactNode } from "react";
import type { ChatBlockDTO } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";
import { blockAssociatedValue, decodeBlockPayload } from "@/lib/chat/block-normalizer";

export interface BlockRenderProps {
  block: ChatBlockDTO;
  activity?: ToolActivityDTO | null;
}

export function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** First non-empty string among the candidates (associated-value fields vary per kind). */
export function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    const text = asString(value);
    if (text) return text;
  }
  return null;
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

/**
 * Read-only selector (§5.2.5): the associated value of a block.  For canonical
 * blocks this is `payload[kind]._0`; for browser-internal / non-canonical blocks
 * it is the flat payload object.  Never a second message model.
 */
export function blockValue(block: ChatBlockDTO): unknown {
  return blockAssociatedValue(block);
}

/** Associated value guaranteed to be an object (empty otherwise). */
export function blockValueObject(block: ChatBlockDTO): Record<string, unknown> {
  return asRecord(blockValue(block));
}

/** Layer error copy (§6.2): only unknown discriminators prompt a version upgrade. */
export function unsupportedCopy(block: ChatBlockDTO): string {
  const status = decodeBlockPayload(block.payload).status;
  return status === "contract_error" ? "内容格式错误" : "此内容需要更新版本查看";
}

/** Safe fallback text for a block, or null when it has no readable text. */
export function fallbackText(block: ChatBlockDTO): string | null {
  const value = blockValue(block);
  if (typeof value === "string") return asString(value);
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return firstString(record.text, record.title, record.message) ?? null;
  }
  return null;
}

/** Generic read-only card shell used by most structured kinds. */
export function ReadOnlyCard({ title, subtitle, children }: { title?: string; subtitle?: string; children?: ReactNode }) {
  return <div className="block block--card">
    {title && <strong className="card-title">{title}</strong>}
    {subtitle && <span className="card-subtitle">{subtitle}</span>}
    {children}
  </div>;
}

export function CardRow({ label, value }: { label: string; value: unknown }) {
  const text = asString(value);
  if (!text) return null;
  return <p className="card-row"><span className="card-row__label">{label}</span><span className="card-row__value">{text}</span></p>;
}

export function SafeText({ value }: { value: unknown }) {
  const text = asString(value);
  if (!text) return null;
  return <span>{text}</span>;
}

/** Safe degraded card for unknown discriminators or malformed known payloads. */
export function UnsupportedBlock({ block }: { block: ChatBlockDTO }) {
  const title = block.kind ? `结构化内容 · ${block.kind}` : "结构化内容";
  return <div className="block block--unknown" role="status"><strong>{title}</strong><p>{unsupportedCopy(block)}</p></div>;
}

/** Lifecycle shell: pending → spinner label, failed → inline error. */
export function BlockShell({ block, children }: { block: ChatBlockDTO; children: ReactNode }) {
  if (block.status === "pending") return <div className="block block--pending" role="status">内容准备中…</div>;
  if (block.status === "failed") return <div className="block block--failed" role="status"><strong>内容生成失败</strong>{fallbackText(block) && <p>{fallbackText(block)}</p>}</div>;
  return <>{children}</>;
}

/** A single-card render failure must never take down the whole message. */
export class BlockErrorBoundary extends Component<{ block: ChatBlockDTO; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { /* intentionally swallowed: isolated cards degrade gracefully */ }
  render() {
    if (this.state.failed) return <UnsupportedBlock block={this.props.block} />;
    return this.props.children;
  }
}