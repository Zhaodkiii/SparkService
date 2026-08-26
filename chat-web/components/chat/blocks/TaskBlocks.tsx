"use client";

import { asString, BlockShell, blockValueObject, CardRow, ReadOnlyCard } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";

function asList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function itemTitle(item: Record<string, unknown>): string {
  return asString(item.title ?? item.name ?? item.label ?? item.text ?? item.question) ?? "选择项";
}

export function TaskCardsBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const items = asList(value.cards ?? value.tasks ?? value.items);
  return <BlockShell block={block}><ReadOnlyCard title={asString(value.title) ?? "任务"}>
    {items.map((item, index) => <CardRow key={index} label={itemTitle(item)} value={item.status ?? item.detail ?? item.subtitle ?? ""} />)}
  </ReadOnlyCard></BlockShell>;
}

export function SmallTaskCardBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const items = asList(value.cards ?? value.tasks ?? value.items);
  return <BlockShell block={block}><ReadOnlyCard title={asString(value.title) ?? "小任务"}>
    {items.map((item, index) => <CardRow key={index} label={itemTitle(item)} value={item.status ?? item.detail ?? ""} />)}
  </ReadOnlyCard></BlockShell>;
}

/** Selection/consent cards render as read-only prompt lists on the web. */
function SelectionList({ block, label }: BlockRenderProps & { label: string }) {
  const value = blockValueObject(block);
  const items = asList(value.cards ?? value.options ?? value.items);
  return <BlockShell block={block}><ReadOnlyCard title={asString(value.title) ?? label}>
    {items.length === 0 ? null : <ul className="block block--list" role="list">{items.map((item, index) => <li key={index}>{itemTitle(item)}</li>)}</ul>}
  </ReadOnlyCard></BlockShell>;
}

export function PendingMemberToolCardsBlock(props: BlockRenderProps) { return <SelectionList {...props} label="成员选择" />; }
export function ToolQuestionCardsBlock(props: BlockRenderProps) { return <SelectionList {...props} label="确认信息" />; }
export function ToolMemberSelectionCardsBlock(props: BlockRenderProps) { return <SelectionList {...props} label="成员选择" />; }
export function HealthResourceCandidateCardsBlock(props: BlockRenderProps) { return <SelectionList {...props} label="健康资料" />; }
export function ToolConsentCardsBlock(props: BlockRenderProps) { return <SelectionList {...props} label="授权确认" />; }
export function LocationPermissionCardsBlock(props: BlockRenderProps) { return <SelectionList {...props} label="位置权限" />; }