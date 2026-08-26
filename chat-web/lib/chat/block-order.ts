import type { ChatBlockDTO } from "@/types/chat";

/**
 * Deterministic ordering for message blocks.
 *
 * Blocks arrive with either a numeric `order_key`, a dotted "bullet" path such
 * as `"1.2.1"`, or `null`. Ordering must be stable across pull/event merges so
 * streaming inserts do not visually jump. The comparator therefore compares on
 * `order_key` first, then falls back to `revision`, then creation time.
 */

function dotSegments(value: string): number[] {
  return value.split(".").map((part) => {
    const number = Number(part);
    return Number.isFinite(number) ? number : 0;
  });
}

function compareOrderKeys(a: ChatBlockDTO, b: ChatBlockDTO): number {
  const left = a.order_key;
  const right = b.order_key;
  if (typeof left === "number" && typeof right === "number") return left - right;
  if (typeof left === "string" && typeof right === "string") {
    const leftSegments = dotSegments(left);
    const rightSegments = dotSegments(right);
    const length = Math.max(leftSegments.length, rightSegments.length);
    for (let index = 0; index < length; index += 1) {
      const diff = (leftSegments[index] ?? 0) - (rightSegments[index] ?? 0);
      if (diff !== 0) return diff;
    }
    return 0;
  }
  if (left !== null && right === null) return -1;
  if (left === null && right !== null) return 1;
  const byRevision = a.revision - b.revision;
  if (byRevision !== 0) return byRevision;
  return (a.created_at ?? "").localeCompare(b.created_at ?? "");
}

/** Return a copy of the blocks sorted in presentation order. */
export function sortBlocksForMessage(blocks: ChatBlockDTO[]): ChatBlockDTO[] {
  return [...blocks].sort(compareOrderKeys);
}