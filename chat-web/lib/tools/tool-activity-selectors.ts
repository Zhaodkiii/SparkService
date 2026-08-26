import type { ChatBlockDTO, ChatRuntimeState } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";
import { isTerminalToolActivityStatus } from "@/types/tool";
import { activityFromToolBlock, isToolActivityBlock } from "@/lib/tools/tool-block-normalizer";

/**
 * P4 selectors: read-only views over the tool activity state. They merge the
 * event-driven projections (toolCallsByRun) with the persisted block view
 * (toolCall/toolResult blocks), preferring the freshest revision of each.
 */

export interface ToolActivityView {
  activity: ToolActivityDTO;
  /** The persisted toolResult block for terminal calls, when synced. */
  resultBlock: ChatBlockDTO | null;
}

/** All tool activities of a run, ordered by (round, call index, id). */
export function orderedToolActivities(state: ChatRuntimeState, runId: string | null | undefined): ToolActivityDTO[] {
  if (!runId) return [];
  const map = state.toolCallsByRun[runId];
  if (!map) return [];
  return Object.values(map).sort(
    (a, b) => a.round_index - b.round_index || a.call_index - b.call_index || a.tool_call_id.localeCompare(b.tool_call_id),
  );
}

export function activeToolActivities(state: ChatRuntimeState, runId: string | null | undefined): ToolActivityDTO[] {
  return orderedToolActivities(state, runId).filter((activity) => !isTerminalToolActivityStatus(activity.status));
}

export function activityByToolCallId(state: ChatRuntimeState | null, runId: string | null | undefined, toolCallId: string | null | undefined): ToolActivityDTO | null {
  if (!state || !runId || !toolCallId) return null;
  return state.toolCallsByRun[runId]?.[toolCallId] ?? null;
}

/**
 * Build the renderable activity view for one tool block. Live event state
 * wins over the persisted block payload; the block acts as fallback (e.g.
 * for historical messages loaded via sync pull, where no run events exist).
 */
export function toolBlockActivityView(
  state: ChatRuntimeState | null,
  runId: string | null | undefined,
  block: ChatBlockDTO,
): ToolActivityDTO | null {
  if (!isToolActivityBlock(block)) return null;
  const live = activityByToolCallId(state, runId, block.tool_call_id ?? (block.payload?.tool_call_id as string | undefined));
  const fromBlock = activityFromToolBlock(block);
  if (live && fromBlock) return live.revision >= fromBlock.revision ? live : fromBlock;
  return live ?? fromBlock;
}

/** Tool blocks of a message, in timeline order. */
export function toolBlocksOfMessage(blocks: ChatBlockDTO[]): ChatBlockDTO[] {
  return blocks.filter(isToolActivityBlock);
}
