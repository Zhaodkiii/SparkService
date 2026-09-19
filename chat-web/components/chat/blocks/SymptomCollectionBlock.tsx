"use client";

import { useMemo, useState } from "react";
import { ChevronDown, CircleCheck, ClipboardList, Sparkles } from "lucide-react";
import { asString, blockValueObject } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";
import type { ChatBlockDTO } from "@/types/chat";
import type { SymptomQuestionCard } from "@/lib/chat/symptom-collection";
import { symptomQuestionCards } from "@/lib/chat/symptom-collection";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function snapshotFor(block: ChatBlockDTO | null): Record<string, unknown> {
  if (!block) return {};
  const value = blockValueObject(block);
  return record(value.snapshot ?? value.symptom_snapshot ?? value.symptomSnapshot ?? value);
}

function displayValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (Array.isArray(value)) return value.map(displayValue).filter(Boolean).join("、") || null;
  return null;
}

function snapshotEntries(snapshot: Record<string, unknown>): Array<[string, string]> {
  const labels = record(snapshot.field_labels ?? snapshot.fieldLabels);
  const values = record(snapshot.values);
  const ignored = new Set(["collection_id", "collectionID", "status", "revision", "required_fields", "requiredFields", "field_labels", "fieldLabels", "analysis_summary", "analysisSummary"]);
  const direct = Object.entries(snapshot)
    .filter(([key, value]) => !ignored.has(key) && displayValue(value))
    .map(([key, value]) => [String(labels[key] ?? key), displayValue(value) as string] as [string, string]);
  const nested = Object.entries(values).filter(([, value]) => displayValue(value)).map(([key, value]) => [String(labels[key] ?? key), displayValue(value) as string] as [string, string]);
  return [...direct, ...nested.filter(([label]) => !direct.some(([existing]) => existing === label))];
}

function titleForField(key: string): string {
  const titles: Record<string, string> = {
    primary_complaint: "主要不适",
    primaryComplaint: "主要不适",
    associated_symptoms: "伴随症状",
    associatedSymptoms: "伴随症状",
    onset_time: "开始时间",
    start_time: "开始时间",
    duration: "持续时间",
    duration_state: "持续时间",
    severity: "严重程度",
    severity_impact: "严重程度",
    accompanying_symptoms: "伴随症状",
    danger_signals: "危险表现",
    trigger: "诱因",
    medication: "用药情况",
  };
  return titles[key] ?? key.replaceAll("_", " ");
}

function statusCopy(status: string, hasPending: boolean): string {
  if (hasPending || status === "collecting" || status === "in_progress") return "正在采集";
  if (status === "cancelled" || status === "expired") return "已结束";
  return "已完成";
}

function progressFor(snapshot: Record<string, unknown>, cards: SymptomQuestionCard[]): number {
  const required = (snapshot.required_fields ?? snapshot.requiredFields);
  if (Array.isArray(required) && required.length) {
    const complete = required.filter((field) => Boolean(displayValue(snapshot[String(field)]))).length;
    return Math.round(complete / required.length * 100);
  }
  const total = cards.flatMap((card) => card.questions);
  const answered = total.filter((question) => cards.some((card) => card.answers.some((answer) => answer.questionId === question.id && (answer.selectedOptionIds.length > 0 || Boolean(answer.otherText))))).length;
  return total.length ? Math.round(answered / total.length * 100) : 100;
}

export function SymptomCollectionCardBlock({ block }: BlockRenderProps) {
  return <SymptomCollectionSummary block={block} questionBlocks={[]} />;
}

export function SymptomCollectionSummary({
  block,
  questionBlocks,
  showActiveQuestions = false,
}: {
  block: ChatBlockDTO | null;
  questionBlocks: ChatBlockDTO[];
  /** 医生端：展示当前待患者填写的采集题目（起始卡 / 进行中轮次）。 */
  showActiveQuestions?: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const cards = useMemo(() => questionBlocks.flatMap(symptomQuestionCards), [questionBlocks]);
  const blockSnapshot = snapshotFor(block);
  const snapshot = Object.keys(blockSnapshot).length ? blockSnapshot : (cards.find((card) => Object.keys(card.snapshot).length)?.snapshot ?? {});
  const summaryValue = block ? blockValueObject(block) : {};
  const status = asString(summaryValue.task_status ?? summaryValue.taskStatus ?? snapshot.status ?? summaryValue.status) ?? "completed";
  const hasPending = cards.some((card) => card.status === "pending" || card.status === "collecting");
  const completed = status === "completed" || status === "submitted" || status === "resolved";
  const progress = completed ? 100 : Number(summaryValue.progress ?? progressFor(snapshot, cards));
  const analysisSummary = asString(snapshot.analysis_summary ?? snapshot.analysisSummary);
  const entries = snapshotEntries(snapshot)
    .map(([label, value]) => [titleForField(label), value] as [string, string])
    .filter(([label], index, all) => all.findIndex(([candidate]) => candidate === label) === index);
  const pendingQuestions = cards
    .filter((card) => card.status === "pending" || card.status === "collecting")
    .flatMap((card) => card.questions);
  const title = showActiveQuestions && hasPending ? "症状采集" : "症状信息汇总";
  const subtitle = showActiveQuestions && hasPending ? "等待患者填写" : statusCopy(status, hasPending);
  // 医生端初步采集（待填题、尚无汇总字段）不展示进度条与百分比。
  const showProgress = !(showActiveQuestions && (hasPending || (!entries.length && !analysisSummary)));

  return <section className="symptom-collection" data-testid="symptom-collection-card">
    <button type="button" className="symptom-collection__header" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
      <span className="symptom-collection__icon"><ClipboardList size={18} /></span>
      <span className="symptom-collection__heading"><strong>{title}</strong><small>{subtitle}</small></span>
      {showProgress ? <span className="symptom-collection__progress">问诊进度 <b>{progress}%</b></span> : null}
      <ChevronDown size={18} className={expanded ? "symptom-collection__chevron symptom-collection__chevron--open" : "symptom-collection__chevron"} />
    </button>
    {expanded ? <div className="symptom-collection__body">
      {showProgress ? <div className="symptom-collection__progressbar"><span style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} /></div> : null}
      {analysisSummary ? <p className="symptom-collection__summary">{analysisSummary}</p> : null}
      {showActiveQuestions && pendingQuestions.length ? (
        <div className="symptom-collection__active-round" aria-label="当前采集题目">
          {pendingQuestions.map((question) => (
            <div className="symptom-collection__question" key={question.id}>
              <p>{question.question}</p>
              {question.options.length ? (
                <div className="symptom-collection__options">
                  {question.options.map((option) => (
                    <span className="symptom-collection__option" key={option.id}>{option.text}</span>
                  ))}
                </div>
              ) : question.allowsOther ? (
                <p className="symptom-collection__waiting">开放描述，等待患者在 App 中填写</p>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      {entries.length ? <div className="symptom-collection__fields">{entries.map(([label, value]) => <div className="symptom-collection__field" key={`${label}-${value}`}><span>{label}</span><strong>{value}</strong></div>)}</div> : (!showActiveQuestions || !pendingQuestions.length) ? <div className="symptom-collection__empty"><Sparkles size={16} /> 已建立症状采集，后续回答会自动补充到这里</div> : null}
      {!hasPending && progress >= 100 ? <div className="symptom-collection__complete"><CircleCheck size={16} /> 症状信息已完整记录，可点击查看详情</div> : null}
    </div> : null}
  </section>;
}
