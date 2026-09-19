import { describe, expect, it } from "vitest";
import { groupSymptomCollectionBlocks, symptomQuestionCards } from "@/lib/chat/symptom-collection";
import { normalizeSyncBlock } from "@/lib/chat/block-normalizer";

function block(id: string, payload: Record<string, unknown>, order_key: number) {
  return normalizeSyncBlock({ id, payload, order_key, status: "ready", revision: 1, node_role: "timeline" });
}

describe("symptom collection presentation", () => {
  it("recognizes the persisted iOS question-card payload", () => {
    const questionBlock = block("questions-1", {
      tool_question_cards: { _0: [{
        id: "round-1",
        status: "submitted",
        prompt: { symptom_collection_id: "collection-1", symptom_snapshot: { collection_id: "collection-1" }, questions: [{ id: "q-1", question: "持续多久？", selection_mode: "single", options: [{ id: "d1", text: "3小时" }] }] },
        answers: [{ question_id: "q-1", selected_option_ids: ["d1"] }],
      }] },
    }, 2100);

    expect(questionBlock.kind).toBe("toolQuestionCards");
    expect(symptomQuestionCards(questionBlock)[0]?.collectionId).toBe("collection-1");
    expect(symptomQuestionCards(questionBlock)[0]?.answers[0]?.selectedOptionIds).toEqual(["d1"]);
  });

  it("keeps the summary first and folds multiple rounds into one unit", () => {
    const summary = block("summary", { symptom_collection_card: { _0: { collection_id: "collection-1", snapshot: { collection_id: "collection-1", primary_complaint: "头晕" } } } }, 2050);
    const round1 = block("round-1", { tool_question_cards: { _0: [{ id: "r1", prompt: { symptom_collection_id: "collection-1", questions: [] }, answers: [], status: "submitted" }] } }, 2100);
    const round2 = block("round-2", { tool_question_cards: { _0: [{ id: "r2", prompt: { symptom_collection_id: "collection-1", questions: [] }, answers: [], status: "submitted" }] } }, 2200);

    const units = groupSymptomCollectionBlocks([round1, summary, round2]);
    expect(units).toHaveLength(1);
    expect(units[0]?.type).toBe("symptomCollection");
    if (units[0]?.type === "symptomCollection") {
      expect(units[0].summaryBlock?.id).toBe("summary");
      expect(units[0].questionBlocks.map((item) => item.id)).toEqual(["round-1", "round-2"]);
    }
  });
});
