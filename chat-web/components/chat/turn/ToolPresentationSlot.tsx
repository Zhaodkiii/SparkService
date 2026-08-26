"use client";

import { renderBlock } from "@/components/chat/blocks/registry";
import { selectPresentationBlocks } from "@/lib/chat/turn-presentation";
import type { ChatBlockDTO } from "@/types/chat";

/**
 * 结构化工具结果插槽（能力六）：只渲染对用户有持续阅读/交互价值的领域结果卡。
 * 去重在 selectPresentationBlocks 完成——通用 `tool` 结果卡若与领域卡共享同一
 * parent_tool_call_id 则被省略，避免“是活动还是结果”两层重复展示。
 */
export function ToolPresentationSlot({ blocks }: { blocks: ChatBlockDTO[] }) {
  const selected = selectPresentationBlocks(blocks);
  if (!selected.length) return null;
  return <div className="turn-presentation">
    {selected.map((block) => <div className="turn-presentation__item" key={block.id}>{renderBlock({ block })}</div>)}
  </div>;
}