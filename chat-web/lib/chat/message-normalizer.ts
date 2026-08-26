import type { ChatBlockDTO } from "@/types/chat";
import { normalizeSyncBlock } from "@/lib/chat/block-normalizer";
import { sortBlocksForMessage } from "@/lib/chat/block-order";

/**
 * Message-level block normalization.
 *
 * Raw blocks from the sync wire are normalized one by one (`normalizeSyncBlock`),
 * then deterministically ordered, and finally assigned a fallback `order_key`
 * for any block the server left without one. This keeps the presentation order
 * stable no matter which field the producing client relied on.
 */
export function normalizeMessageBlocks(rawBlocks: unknown[]): ChatBlockDTO[] {
  const blocks = rawBlocks
    .filter((raw): raw is Record<string, unknown> => Boolean(raw) && typeof raw === "object" && !Array.isArray(raw))
    .map((raw) => normalizeSyncBlock(raw));
  return sortBlocksForMessage(blocks).map((block, index) => (
    block.order_key === null ? { ...block, order_key: index + 1 } : block
  ));
}