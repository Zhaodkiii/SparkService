import type { ChatBlockDTO, ChatUsageSummary, TurnActionPermissions, TurnSummary, TurnUsageSummary } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";
import { sortBlocksForMessage } from "@/lib/chat/block-order";
import { extractAnswerText } from "@/lib/chat/answer-text";
import { activityFromToolBlock, isToolActivityBlock } from "@/lib/tools/tool-block-normalizer";
import { blockAssociatedValue } from "@/lib/chat/block-normalizer";

/**
 * Turn presentation (能力一/六)：把一条消息的 Block 按“活动 / 正文 /
 * 结构化结果”归类，并用稳定的 order/revision/id 排序。UI 只消费这个投影，
 * 不在这里解析 Provider 原始 payload。
 */

export type TurnBlockCategory = "thinking" | "activity" | "content" | "presentation";

export interface TurnPresentation {
  messageId: string;
  role: "user" | "assistant" | "system";
  thinkingBlocks: ChatBlockDTO[];
  activityBlocks: ChatBlockDTO[];
  contentBlocks: ChatBlockDTO[];
  presentationBlocks: ChatBlockDTO[];
  orderedBlocks: ChatBlockDTO[];
  hasText: boolean;
}

const CONTENT_KINDS: ReadonlySet<string> = new Set(["text", "html", "translatedText"]);

export function classifyTurnBlock(block: ChatBlockDTO): TurnBlockCategory {
  if (block.kind === "deepThought") return "thinking";
  if (isToolActivityBlock(block)) return "activity";
  if (CONTENT_KINDS.has(block.kind)) return "content";
  return "presentation";
}

/** Final user-visible text of a turn (copy / regenerate scope). */
export function turnVisibleText(blocks: ChatBlockDTO[]): string {
  return extractAnswerText(blocks);
}

export function buildTurnPresentation(
  blocks: ChatBlockDTO[],
  messageId: string,
  role: "user" | "assistant" | "system",
): TurnPresentation {
  const orderedBlocks = sortBlocksForMessage(blocks);
  const thinkingBlocks: ChatBlockDTO[] = [];
  const activityBlocks: ChatBlockDTO[] = [];
  const contentBlocks: ChatBlockDTO[] = [];
  const presentationBlocks: ChatBlockDTO[] = [];
  for (const block of orderedBlocks) {
    const category = classifyTurnBlock(block);
    if (category === "thinking") thinkingBlocks.push(block);
    else if (category === "activity") activityBlocks.push(block);
    else if (category === "content") contentBlocks.push(block);
    else presentationBlocks.push(block);
  }
  const hasText = turnVisibleText(contentBlocks) !== "";
  return { messageId, role, thinkingBlocks, activityBlocks, contentBlocks, presentationBlocks, orderedBlocks, hasText };
}

/**
 * Deduplicate presentation cards (能力六)：当“通用 `tool` 结果卡”与某个领域结果卡
 * 共享同一 parent_tool_call_id 时，省略通用卡，保留领域卡，避免同一结果展示两次。
 * 失败且没有可读 payload 的结果卡也不进入插槽，避免空白卡。
 */
function isBlankFailedPresentation(block: ChatBlockDTO): boolean {
  if (block.status !== "failed") return false;
  const payload = block.payload;
  if (!payload || typeof payload !== "object") return true;
  return Object.keys(payload).length === 0;
}

export function selectPresentationBlocks(presentationBlocks: ChatBlockDTO[]): ChatBlockDTO[] {
  const domainCallIds = new Set<string>();
  for (const block of presentationBlocks) {
    if (block.kind === "tool" || isBlankFailedPresentation(block)) continue;
    const callId = block.parent_tool_call_id ?? block.tool_call_id;
    if (typeof callId === "string" && callId) domainCallIds.add(callId);
  }
  return presentationBlocks.filter((block) => {
    if (isBlankFailedPresentation(block)) return false;
    if (block.kind !== "tool") return true;
    const callId = block.parent_tool_call_id ?? block.tool_call_id;
    return !(typeof callId === "string" && callId && domainCallIds.has(callId));
  });
}

function interactionIdFromBlock(block: ChatBlockDTO): string {
  const value = blockAssociatedValue(block);
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const id = (value as Record<string, unknown>).interaction_id;
    if (typeof id === "string" && id) return id;
  }
  return block.id;
}

export function dedupeToolQuestionCards(blocks: ChatBlockDTO[]): ChatBlockDTO[] {
  const latest = new Map<string, ChatBlockDTO>();
  for (const block of blocks) {
    if (block.kind !== "toolQuestionCards") continue;
    const id = interactionIdFromBlock(block);
    const current = latest.get(id);
    if (!current || Number(block.revision) >= Number(current.revision)) latest.set(id, block);
  }
  return blocks.filter((block) => {
    if (block.kind !== "toolQuestionCards") return true;
    return latest.get(interactionIdFromBlock(block)) === block;
  });
}

/**
 * Merge tool activity rows from persisted toolCall/toolResult blocks with the
 * live event projection (per call id). A tool call and its result collapse into
 * a single row; duplicate call ids never produce two rows.
 */
export function collectToolActivityRows(
  blocks: ChatBlockDTO[],
  activityByCallId?: (toolCallId: string | null | undefined) => ToolActivityDTO | null,
): ToolActivityDTO[] {
  const rows: ToolActivityDTO[] = [];
  const seen = new Set<string>();
  for (const block of blocks) {
    if (!isToolActivityBlock(block)) continue;
    const toolCallId = block.tool_call_id ?? (block.payload?.tool_call_id as string | undefined);
    const live = activityByCallId?.(toolCallId) ?? null;
    const fromBlock = activityFromToolBlock(block);
    const merged = live && fromBlock ? (live.revision >= fromBlock.revision ? live : fromBlock) : (live ?? fromBlock);
    if (merged && !seen.has(merged.tool_call_id)) {
      seen.add(merged.tool_call_id);
      rows.push(merged);
    }
  }
  return rows.sort(
    (a, b) => a.round_index - b.round_index || a.call_index - b.call_index || a.tool_call_id.localeCompare(b.tool_call_id),
  );
}

/** 回合耗时的人类可读展示（能力五状态头），例如 `4s` / `1m 3s`。 */
export function formatTurnDuration(ms: number | null | undefined): string | null {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) {
    const tenths = Math.round(seconds * 10) / 10;
    if (seconds < 10 && !Number.isInteger(tenths)) return `${tenths.toFixed(1)}s`;
    return `${Math.round(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

/**
 * 能力五：合并 Sync 的 `usage_summary` 与 `turn_summary.usage`，输出 UI 用量。
 * 优先使用带可靠计价来源的 `turn_summary.usage`；退化时不展示伪费用。
 */
export function normalizeUsage(
  usageSummary: ChatUsageSummary | null | undefined,
  turnUsage: TurnUsageSummary | null | undefined,
): TurnUsageSummary | null {
  if (turnUsage) return turnUsage;
  if (!usageSummary) return null;
  const hasAny = usageSummary.prompt_tokens > 0 || usageSummary.completion_tokens > 0 || usageSummary.reasoning_tokens > 0 || usageSummary.model_calls > 0 || usageSummary.tool_calls > 0;
  if (!hasAny) return null;
  return {
    prompt_tokens: usageSummary.prompt_tokens || null,
    completion_tokens: usageSummary.completion_tokens || null,
    reasoning_tokens: usageSummary.reasoning_tokens || null,
    tool_calls: usageSummary.tool_calls || null,
    model_calls: usageSummary.model_calls || null,
    amount: null,
    currency: null,
    price_version: null,
  };
}

/** 能力五：由回合摘要推导操作权限；无摘要时禁用无法安全执行的历史操作。 */
export function deriveActionPermissions(turnSummary: TurnSummary | null | undefined): TurnActionPermissions {
  return {
    regenerateAllowed: turnSummary ? turnSummary.regenerate_allowed : false,
    deleteAllowed: turnSummary ? turnSummary.delete_allowed : false,
  };
}