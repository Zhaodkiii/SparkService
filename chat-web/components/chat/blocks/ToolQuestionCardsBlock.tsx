"use client";

import { useMemo, useState } from "react";
import { asRecord, asString, blockValueObject } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";
import { usePendingInteraction } from "@/hooks/usePendingInteraction";
import type {
  InteractionAnswerDTO,
  InteractionQuestion,
  InteractionQuestionOption,
  PendingInteractionDTO,
  PendingInteractionRequest,
} from "@/types/interaction";

function asQuestions(request: PendingInteractionRequest | Record<string, unknown> | undefined): InteractionQuestion[] {
  const questions = request && Array.isArray(request.questions) ? request.questions : [];
  return questions.filter((item): item is InteractionQuestion => Boolean(item && typeof item === "object" && item.id));
}

function optionLabel(option: InteractionQuestionOption | string | undefined): string {
  if (!option) return "";
  if (typeof option === "string") return option;
  return asString(option.label) ?? "";
}

function interactionFromBlock(value: Record<string, unknown>): PendingInteractionDTO | null {
  const interactionId = asString(value.interaction_id);
  const runId = asString(value.run_id);
  if (!interactionId || !runId) return null;
  const request = asRecord(value.request) as PendingInteractionRequest;
  return {
    run_id: runId,
    interaction_id: interactionId,
    interaction_key: asString(value.interaction_key) ?? "",
    kind: asString(value.kind) ?? "ask_user",
    status: asString(value.status) ?? "pending",
    tool_call_id: asString(value.tool_call_id),
    tool_name: asString(value.tool_name) ?? "ask_user",
    tool_version: asString(value.tool_version) ?? "v1",
    schema_version: typeof value.schema_version === "number" ? value.schema_version : 2,
    question_ids: Array.isArray(value.question_ids) ? value.question_ids.map(String) : [],
    request,
    expires_at: asString(value.expires_at),
  };
}

function statusCopy(status: string | undefined): string {
  if (status === "resolved") return "已确认";
  if (status === "refused") return "已跳过";
  if (status === "expired") return "已过期";
  if (status === "cancelled") return "已取消";
  if (status === "claimed") return "处理中";
  return "需要你确认";
}

export interface AskUserQuestionFormProps {
  interaction: PendingInteractionDTO;
  answersPreview?: InteractionAnswerDTO[];
  locked?: boolean;
  submitting?: boolean;
  error?: string | null;
  onSubmit?: (answers: InteractionAnswerDTO[]) => Promise<unknown> | unknown;
  onRefuse?: () => Promise<unknown> | unknown;
}

export function AskUserQuestionForm({
  interaction,
  answersPreview,
  locked = false,
  submitting = false,
  error,
  onSubmit,
  onRefuse,
}: AskUserQuestionFormProps) {
  const questions = asQuestions(interaction.request);
  const [selected, setSelected] = useState<Record<string, number[]>>({});
  const [freeText, setFreeText] = useState<Record<string, string>>({});
  const [localError, setLocalError] = useState<string | null>(null);
  const disabled = locked || submitting || !onSubmit;
  const intro = asString(interaction.request?.intro);
  const resolved = !["pending", "claimed"].includes(String(interaction.status));

  const complete = useMemo(() => {
    return questions.every((question) => {
      const indexes = selected[question.id] ?? [];
      const text = (freeText[question.id] ?? "").trim();
      return indexes.length > 0 || (question.allow_free_text !== false && Boolean(text));
    });
  }, [freeText, questions, selected]);

  function toggle(question: InteractionQuestion, index: number) {
    if (disabled) return;
    setSelected((current) => {
      const existing = current[question.id] ?? [];
      if (question.multi_select) {
        const next = existing.includes(index) ? existing.filter((item) => item !== index) : [...existing, index].sort((a, b) => a - b);
        return { ...current, [question.id]: next };
      }
      return { ...current, [question.id]: [index] };
    });
    setLocalError(null);
  }

  async function handleSubmit() {
    if (!onSubmit || disabled) return;
    if (!complete) {
      setLocalError("请完成所有问题后再提交");
      return;
    }
    const answers: InteractionAnswerDTO[] = questions.map((question) => {
      const indexes = selected[question.id] ?? [];
      const options = question.options ?? [];
      return {
        question_id: question.id,
        selected_option_indexes: indexes,
        selected_labels: indexes.map((index) => optionLabel(options[index])),
        free_text: (freeText[question.id] ?? "").trim(),
      };
    });
    await onSubmit(answers);
  }

  if (resolved) {
    const preview = answersPreview ?? [];
    return <section className={`ask-user-card ask-user-card--${interaction.status}`} data-testid="ask-user-card" aria-live="polite">
      <p className="ask-user-card__status">{statusCopy(String(interaction.status))}</p>
      {intro ? <p className="ask-user-card__intro">{intro}</p> : null}
      {questions.map((question) => {
        const answer = preview.find((item) => item.question_id === question.id);
        const labels = answer?.selected_labels?.filter(Boolean) ?? [];
        return <div className="ask-user-card__question" key={question.id}>
          {question.header ? <span className="ask-user-card__header">{question.header}</span> : null}
          <p className="ask-user-card__prompt">{question.prompt}</p>
          <p className="ask-user-card__summary">{labels.length ? labels.join("、") : answer?.has_free_text || answer?.free_text ? "已补充说明" : "未选择"}</p>
        </div>;
      })}
    </section>;
  }

  return <section className={`ask-user-card${disabled ? " ask-user-card--locked" : ""}`} data-testid="ask-user-card">
    <p className="ask-user-card__status">{statusCopy(String(interaction.status))}</p>
    {intro ? <p className="ask-user-card__intro">{intro}</p> : null}
    {questions.map((question) => {
      const indexes = selected[question.id] ?? [];
      const options = question.options ?? [];
      return <fieldset className="ask-user-card__question" key={question.id} disabled={disabled}>
        {question.header ? <legend className="ask-user-card__header">{question.header}</legend> : null}
        <p className="ask-user-card__prompt">{question.prompt}</p>
        {options.length ? <div className="ask-user-card__options" role={question.multi_select ? "group" : "radiogroup"}>
          {options.map((option, index) => {
            const label = optionLabel(option);
            const checked = indexes.includes(index);
            return <button
              type="button"
              className={`ask-user-card__option${checked ? " ask-user-card__option--selected" : ""}`}
              key={`${question.id}-${index}`}
              aria-pressed={checked}
              aria-checked={checked}
              role={question.multi_select ? "checkbox" : "radio"}
              disabled={disabled}
              onClick={() => toggle(question, index)}
            >{label}</button>;
          })}
        </div> : null}
        {question.allow_free_text !== false ? <textarea
          className="ask-user-card__text"
          value={freeText[question.id] ?? ""}
          placeholder={asString(question.placeholder) ?? "补充说明（可选）"}
          disabled={disabled}
          rows={2}
          onChange={(event) => {
            setFreeText((current) => ({ ...current, [question.id]: event.target.value }));
            setLocalError(null);
          }}
        /> : null}
      </fieldset>;
    })}
    {localError || error ? <p className="ask-user-card__error" role="alert">{localError || error}</p> : null}
    <div className="ask-user-card__actions">
      <button type="button" className="ask-user-card__submit" disabled={disabled || !complete} onClick={() => void handleSubmit()}>
        {submitting ? "提交中…" : "提交"}
      </button>
      {onRefuse ? <button type="button" className="ask-user-card__skip" disabled={disabled} onClick={() => void onRefuse()}>跳过</button> : null}
    </div>
  </section>;
}

export function ToolQuestionCardsBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const fromBlock = interactionFromBlock(value);
  const preview = Array.isArray(value.answers) ? value.answers.filter((item): item is InteractionAnswerDTO => Boolean(item && typeof item === "object") && typeof (item as InteractionAnswerDTO).question_id === "string") : [];
  const live = usePendingInteraction(fromBlock?.interaction_id, fromBlock);
  const interaction = live.interaction ?? fromBlock;
  if (!interaction) return null;
  return <AskUserQuestionForm
    interaction={interaction}
    answersPreview={preview}
    locked={live.locked}
    submitting={live.submitting}
    error={live.error}
    onSubmit={live.open ? live.submit : undefined}
    onRefuse={live.open ? live.refuse : undefined}
  />;
}
