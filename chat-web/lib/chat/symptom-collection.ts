import type { ChatBlockDTO } from "@/types/chat";
import { blockAssociatedValue } from "@/lib/chat/block-normalizer";

export interface SymptomOption {
  id: string;
  text: string;
}

export interface SymptomQuestion {
  id: string;
  question: string;
  fieldKey: string | null;
  selectionMode: "single" | "multiple";
  allowsOther: boolean;
  options: SymptomOption[];
}

export interface SymptomAnswer {
  questionId: string;
  selectedOptionIds: string[];
  otherText: string | null;
}

export interface SymptomQuestionCard {
  id: string;
  collectionId: string;
  status: string;
  resultText: string | null;
  snapshot: Record<string, unknown>;
  questions: SymptomQuestion[];
  answers: SymptomAnswer[];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function firstText(...values: unknown[]): string | null {
  for (const value of values) {
    const result = text(value);
    if (result) return result;
  }
  return null;
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function snapshotFrom(value: Record<string, unknown>): Record<string, unknown> {
  const prompt = record(value.prompt);
  return record(value.snapshot ?? value.symptom_snapshot ?? value.symptomSnapshot ?? prompt.symptom_snapshot ?? prompt.symptomSnapshot);
}

export function collectionIdFromValue(value: unknown): string | null {
  const root = record(value);
  const prompt = record(root.prompt);
  const snapshot = snapshotFrom(root);
  return firstText(
    root.collection_id,
    root.collectionID,
    prompt.symptom_collection_id,
    prompt.symptomCollectionId,
    snapshot.collection_id,
    snapshot.collectionID,
  );
}

function normalizeQuestion(value: unknown): SymptomQuestion | null {
  const item = record(value);
  const id = firstText(item.id, item.question_id, item.questionID);
  const question = firstText(item.question, item.prompt, item.text);
  if (!id || !question) return null;
  const selectionMode = item.selection_mode === "multiple" || item.selectionMode === "multiple" || item.multi_select === true ? "multiple" : "single";
  const options = array(item.options).map((option) => {
    const entry = record(option);
    const optionId = firstText(entry.id, entry.option_id, entry.optionID, entry.value);
    const optionText = firstText(entry.text, entry.label, entry.title, typeof option === "string" ? option : null);
    return optionId && optionText ? { id: optionId, text: optionText } : null;
  }).filter((option): option is SymptomOption => Boolean(option));
  return {
    id,
    question,
    fieldKey: firstText(item.field_key, item.fieldKey),
    selectionMode,
    allowsOther: item.allows_other !== false && item.allowsOther !== false,
    options,
  };
}

function normalizeAnswer(value: unknown): SymptomAnswer | null {
  const item = record(value);
  const questionId = firstText(item.question_id, item.questionID, item.id);
  if (!questionId) return null;
  const selected = array(item.selected_option_ids ?? item.selectedOptionIds ?? item.option_ids).map(String).filter(Boolean);
  return { questionId, selectedOptionIds: selected, otherText: firstText(item.other_text, item.otherText, item.free_text) };
}

export function symptomQuestionCards(block: ChatBlockDTO): SymptomQuestionCard[] {
  if (block.kind !== "toolQuestionCards") return [];
  const value = blockAssociatedValue(block);
  const candidates = Array.isArray(value) ? value : [value];
  return candidates.map((candidate) => {
    const item = record(candidate);
    const prompt = record(item.prompt);
    const collectionId = collectionIdFromValue(item);
    if (!collectionId) return null;
    const questions = array(prompt.questions ?? item.questions).map(normalizeQuestion).filter((question): question is SymptomQuestion => Boolean(question));
    const answers = array(item.answers).map(normalizeAnswer).filter((answer): answer is SymptomAnswer => Boolean(answer));
    return {
      id: firstText(item.id, item.completion_id, item.completionID) ?? `${block.id}-${collectionId}`,
      collectionId,
      status: firstText(item.status) ?? "pending",
      resultText: firstText(item.result_text, item.resultText),
      snapshot: snapshotFrom(item),
      questions,
      answers,
    } satisfies SymptomQuestionCard;
  }).filter((card): card is SymptomQuestionCard => Boolean(card));
}

export function symptomCollectionId(block: ChatBlockDTO): string | null {
  if (block.kind === "symptomCollectionCard") return collectionIdFromValue(blockAssociatedValue(block));
  return symptomQuestionCards(block)[0]?.collectionId ?? null;
}

export function isSymptomQuestionBlock(block: ChatBlockDTO): boolean {
  return symptomQuestionCards(block).length > 0;
}

export interface SymptomCollectionUnit {
  type: "symptomCollection";
  collectionId: string;
  summaryBlock: ChatBlockDTO | null;
  questionBlocks: ChatBlockDTO[];
  firstIndex: number;
}

export interface PresentationBlockUnit {
  type: "block";
  block: ChatBlockDTO;
  firstIndex: number;
}

export type PresentationUnit = SymptomCollectionUnit | PresentationBlockUnit;

/**
 * Reconstruct the client presentation model from persisted Web blocks. The
 * server stores the summary and each question round as separate blocks; the
 * UI must render one stable summary card and append all rounds below it.
 */
export function groupSymptomCollectionBlocks(blocks: ChatBlockDTO[]): PresentationUnit[] {
  const groups = new Map<string, SymptomCollectionUnit>();
  const consumed = new Set<string>();
  const units: PresentationUnit[] = [];

  blocks.forEach((block, index) => {
    const collectionId = symptomCollectionId(block);
    if (!collectionId) {
      units.push({ type: "block", block, firstIndex: index });
      return;
    }
    let group = groups.get(collectionId);
    if (!group) {
      group = { type: "symptomCollection", collectionId, summaryBlock: null, questionBlocks: [], firstIndex: index };
      groups.set(collectionId, group);
      units.push(group);
    }
    group.firstIndex = Math.min(group.firstIndex, index);
    if (block.kind === "symptomCollectionCard") group.summaryBlock = block;
    else if (isSymptomQuestionBlock(block)) group.questionBlocks.push(block);
    consumed.add(block.id);
  });

  return units.filter((unit) => unit.type === "symptomCollection" || !consumed.has(unit.block.id)).sort((a, b) => a.firstIndex - b.firstIndex);
}
