import type { ChatBlockDTO, WebToolActivityBlockKind } from "@/types/chat";
import { WEB_TOOL_ACTIVITY_BLOCK_KINDS } from "@/types/chat";
import { blockAssociatedValue } from "@/lib/chat/block-normalizer";
import { normalizeToolActivity } from "@/lib/tools/tool-activity-reducer";
import type { ToolActivityDTO } from "@/types/tool";

/**
 * Tool block projection (CHAT-DATA-026 §6).
 *
 * Two shapes feed the activity layer:
 *
 * 1. Canonical iOS `tool` blocks, whose associated value (`payload.tool`) is
 *    `{ name, content, invocation_arguments }`.  These are the single message
 *    model's tool invocation and must be classified as activity, not text.
 * 2. Browser-internal `toolCall` / `toolResult` projections produced by the P4
 *    tool activity loop.  They carry only safe fields (display_args,
 *    result_preview, source_refs, error projection) and are never on the wire.
 *
 * This module never reads raw `arguments` or result hashes.
 */

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

export function isToolActivityBlock(block: ChatBlockDTO): boolean {
  if (block.kind === "tool") return true;
  return WEB_TOOL_ACTIVITY_BLOCK_KINDS.includes(block.kind as WebToolActivityBlockKind);
}

/** Extract the canonical `tool` associated value ({ name, content, ... }). */
export function canonicalToolValue(block: ChatBlockDTO): Record<string, unknown> {
  return objectValue(blockAssociatedValue(block));
}

/**
 * Build an activity-shaped view from a tool block, canonical or internal.
 * Returns null for non-tool blocks or malformed payloads.
 */
export function activityFromToolBlock(block: ChatBlockDTO): ToolActivityDTO | null {
  if (!isToolActivityBlock(block)) return null;

  if (block.kind === "tool") {
    const value = canonicalToolValue(block);
    const toolCallId = block.tool_call_id
      || block.parent_tool_call_id
      || (block.anchor?.type === "toolCall" ? block.anchor.value : "")
      || `tool:${block.id}`;
    const name = stringValue(value.name) || "unknown_tool";
    return normalizeToolActivity({
      tool_call_id: toolCallId,
      name,
      version: "v1",
      display_name: stringValue(value.name) || "服务工具",
      target: "server",
      status: "completed",
      round_index: 0,
      call_index: 0,
      revision: block.revision,
      display_args: objectValue(value.invocation_arguments),
      result_preview: nullableString(value.content),
      source_refs: [],
      error: null,
      duplicate_of: null,
      started_at: null,
      finished_at: null,
    });
  }

  const payload = block.payload && typeof block.payload === "object" ? block.payload : {};
  const payloadStatus = typeof payload.status === "string" ? payload.status : null;
  let status: string;
  if (block.kind === "toolResult") {
    status = payloadStatus === "failed" || block.status === "failed" ? "failed" : "completed";
  } else if (block.status === "failed") {
    status = "cancelled";
  } else {
    status = payloadStatus ?? "requested";
  }
  return normalizeToolActivity({
    ...payload,
    tool_call_id: payload.tool_call_id ?? block.tool_call_id,
    status,
  });
}

/**
 * One-line safe summary for a tool block, used by the activity panel and as
 * the disclosure header. Falls back to generic copy when the payload is thin.
 */
export function toolBlockSummaryLine(block: ChatBlockDTO): string {
  if (block.kind === "tool") {
    const name = stringValue(canonicalToolValue(block).name) || "服务端工具";
    return `${name} · 工具执行记录`;
  }
  const activity = activityFromToolBlock(block);
  if (!activity) return block.kind === "toolResult" ? "工具执行结束" : "正在使用服务端工具";
  if (activity.duplicate_of) return `${activity.display_name} · 已复用相同请求的结果`;
  if (activity.error) return `${activity.display_name} · 执行失败`;
  if (activity.result_preview) return `${activity.display_name} · ${activity.result_preview}`;
  if (activity.status === "running") return `${activity.display_name} · 执行中`;
  if (activity.status === "requested") return `${activity.display_name} · 准备执行`;
  return activity.display_name;
}
