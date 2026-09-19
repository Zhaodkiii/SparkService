"use client";

import { renderBlock } from "@/components/chat/blocks/registry";
import { selectPresentationBlocks, dedupeToolQuestionCards } from "@/lib/chat/turn-presentation";
import type { ChatBlockDTO } from "@/types/chat";
import type { HealthResourceReference } from "@/types/medical-resource";
import { groupSymptomCollectionBlocks } from "@/lib/chat/symptom-collection";
import { SymptomCollectionSummary } from "@/components/chat/blocks/SymptomCollectionBlock";

/**
 * 结构化工具结果插槽（能力六）：只渲染对用户有持续阅读/交互价值的领域结果卡。
 * 去重在 selectPresentationBlocks 完成——通用 `tool` 结果卡若与领域卡共享同一
 * parent_tool_call_id 则被省略，避免“是活动还是结果”两层重复展示。
 */
export function ToolPresentationSlot({ blocks, onHealthResourceOpen }: { blocks: ChatBlockDTO[]; onHealthResourceOpen?: (reference: HealthResourceReference) => void }) {
  const selected = dedupeToolQuestionCards(selectPresentationBlocks(blocks));
  const units = groupSymptomCollectionBlocks(selected);
  if (!units.length) return null;
  return <div className="turn-presentation">
    {units.map((unit) => <div className="turn-presentation__item" key={unit.type === "block" ? unit.block.id : `symptom-${unit.collectionId}`}>
      {unit.type === "block" ? renderBlock({ block: unit.block, onHealthResourceOpen }) : <SymptomCollectionSummary block={unit.summaryBlock} questionBlocks={unit.questionBlocks} />}
    </div>)}
  </div>;
}
