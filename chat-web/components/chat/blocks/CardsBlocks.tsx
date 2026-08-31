"use client";

import { CloudSun } from "lucide-react";
import { asString, BlockShell, blockValueObject, CardRow, ReadOnlyCard } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";

function asList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function itemTitle(item: Record<string, unknown>): string {
  return asString(item.title ?? item.name ?? item.label ?? item.text) ?? "条目";
}

export function HealthCardsBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const items = asList(value.cards ?? value.items);
  return <BlockShell block={block}><ReadOnlyCard title={asString(value.title) ?? "健康卡片"}>
    {items.map((item, index) => <CardRow key={index} label={itemTitle(item)} value={item.value ?? item.detail ?? item.subtitle ?? ""} />)}
  </ReadOnlyCard></BlockShell>;
}

export function StructuredHealthCardsBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const items = asList(value.cards ?? value.items);
  return <BlockShell block={block}><ReadOnlyCard title={asString(value.title) ?? "结构化健康指标"}>
    {items.map((item, index) => <CardRow key={index} label={itemTitle(item)} value={item.value ?? item.detail ?? item.subtitle ?? ""} />)}
  </ReadOnlyCard></BlockShell>;
}

export function NutritionCardsBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const items = asList(value.cards ?? value.entries ?? value.items);
  return <BlockShell block={block}><ReadOnlyCard title={asString(value.title) ?? "饮食营养"}>
    {items.map((item, index) => <CardRow key={index} label={itemTitle(item)} value={item.value ?? item.calories ?? item.detail ?? ""} />)}
  </ReadOnlyCard></BlockShell>;
}

export function SearchSummaryBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const query = asString(value.query) ?? asString(value.keyword);
  const summary = asString(value.summary) ?? asString(value.text) ?? asString(value.detail);
  const references = asList(value.references);
  return <BlockShell block={block}><ReadOnlyCard title="搜索结果总结" subtitle={query ?? undefined}>
    {summary ? <p>{summary}</p> : null}
    {references.length > 0 ? <ul className="block block--list" role="list">{references.map((ref, index) => <li key={index}>{asString(ref.title) ?? "来源"}{ref.url ? <a href={asString(ref.url) ?? "#"} target="_blank" rel="noreferrer noopener">查看</a> : null}</li>)}</ul> : null}
  </ReadOnlyCard></BlockShell>;
}

export function WeatherConfigCardBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const city = asString(value.city) ?? asString(value.location);
  const unit = asString(value.unit) ?? asString(value.temperature_unit);
  return <BlockShell block={block}><ReadOnlyCard title="天气设置" subtitle={city ?? undefined}><CloudSun size={16} />{unit && <CardRow label="温度单位" value={unit} />}</ReadOnlyCard></BlockShell>;
}