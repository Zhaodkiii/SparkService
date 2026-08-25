import type { CreateTurnContextInput, TurnContextDraft, TurnContextItem } from "@/types/context";

export function emptyTurnContextDraft(threadId: string | null): TurnContextDraft {
  return { threadId, contextParentMessageId: null, items: [] };
}

export function addTurnContextItem(draft: TurnContextDraft, item: TurnContextItem): TurnContextDraft {
  if (draft.items.some((current) => current.key === item.key) || draft.items.length >= 16) return draft;
  return { ...draft, items: [...draft.items, item] };
}

export function removeTurnContextItem(draft: TurnContextDraft, key: string): TurnContextDraft {
  return { ...draft, items: draft.items.filter((item) => item.key !== key) };
}

export function toCreateTurnContextInput(draft: TurnContextDraft, revision: number): CreateTurnContextInput {
  return {
    preferencesRevision: revision,
    contextParentMessageId: draft.contextParentMessageId,
    references: draft.items.filter((item): item is Extract<TurnContextItem, { kind: "health_resource" }> => item.kind === "health_resource" && item.status === "ready").map((item) => ({ type: "health_resource", resource_type: item.resourceType, resource_id: item.resourceId })),
    attachments: draft.items.filter((item): item is Extract<TurnContextItem, { kind: "attachment" }> => item.kind === "attachment" && item.status === "ready").map((item) => ({ file_id: item.fileId })),
  };
}
