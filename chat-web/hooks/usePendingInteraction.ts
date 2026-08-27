"use client";

import { useCallback, useMemo, useState } from "react";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { isOpenInteractionStatus, type InteractionAnswerDTO, type PendingInteractionDTO } from "@/types/interaction";

export function usePendingInteraction(interactionId: string | null | undefined, fallback?: PendingInteractionDTO | null) {
  const live = useOptionalRunControl();
  const runId = live?.run?.id ?? fallback?.run_id ?? "";
  const fromState = runId && interactionId ? live?.state.interactionsByRun[runId]?.[interactionId] : undefined;
  const interaction = fromState ?? fallback ?? null;
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = isOpenInteractionStatus(interaction?.status);
  const locked = !open || submitting || !live?.submitInteraction;

  const submit = useCallback(async (answers: InteractionAnswerDTO[]) => {
    if (!live?.submitInteraction || !interaction) return { ok: false as const, error: "当前无法提交" };
    setSubmitting(true);
    setError(null);
    try {
      const result = await live.submitInteraction(interaction.interaction_id, {
        run_id: interaction.run_id,
        interaction_key: interaction.interaction_key,
        schema_version: interaction.schema_version,
        resolution: "answered",
        question_ids: answers.map((item) => item.question_id),
        answers,
      });
      if (!result.ok) setError(result.error);
      return result;
    } finally {
      setSubmitting(false);
    }
  }, [interaction, live]);

  const refuse = useCallback(async () => {
    if (!live?.refuseInteraction || !interaction) return { ok: false as const, error: "当前无法跳过" };
    setSubmitting(true);
    setError(null);
    try {
      const result = await live.refuseInteraction(interaction.interaction_id);
      if (!result.ok) setError(result.error);
      return result;
    } finally {
      setSubmitting(false);
    }
  }, [interaction, live]);

  return useMemo(
    () => ({ interaction, submitting, error, locked, open, submit, refuse }),
    [error, interaction, locked, open, refuse, submit, submitting],
  );
}
