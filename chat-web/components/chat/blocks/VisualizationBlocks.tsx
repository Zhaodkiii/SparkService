"use client";

import { MapPin } from "lucide-react";
import type { ChatBlockDTO } from "@/types/chat";
import { asString, BlockShell, blockValueObject, CardRow, ReadOnlyCard } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";

function summaryOf(block: ChatBlockDTO, label: string): string {
  const value = blockValueObject(block);
  return asString(value.summary) ?? asString(value.text) ?? asString(value.detail) ?? asString(value.title) ?? label;
}

export function SleepVisualizationBlock({ block }: BlockRenderProps) {
  return <BlockShell block={block}><ReadOnlyCard title="睡眠"><CardRow label="概览" value={summaryOf(block, "睡眠数据")} /></ReadOnlyCard></BlockShell>;
}
export function StepVisualizationBlock({ block }: BlockRenderProps) {
  return <BlockShell block={block}><ReadOnlyCard title="步数"><CardRow label="概览" value={summaryOf(block, "步数数据")} /></ReadOnlyCard></BlockShell>;
}
export function EnergyVisualizationBlock({ block }: BlockRenderProps) {
  return <BlockShell block={block}><ReadOnlyCard title="精力"><CardRow label="概览" value={summaryOf(block, "精力数据")} /></ReadOnlyCard></BlockShell>;
}
export function NutritionReadVisualizationBlock({ block }: BlockRenderProps) {
  return <BlockShell block={block}><ReadOnlyCard title="营养解读"><CardRow label="概览" value={summaryOf(block, "营养数据")} /></ReadOnlyCard></BlockShell>;
}
export function WorkoutVisualizationBlock({ block }: BlockRenderProps) {
  return <BlockShell block={block}><ReadOnlyCard title="运动"><CardRow label="概览" value={summaryOf(block, "运动数据")} /></ReadOnlyCard></BlockShell>;
}
export function WeatherVisualizationBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const place = asString(value.city) ?? asString(value.location);
  return <BlockShell block={block}><ReadOnlyCard title="天气" subtitle={place ?? undefined}><CardRow label="概览" value={summaryOf(block, "天气数据")} /></ReadOnlyCard></BlockShell>;
}

export function MapRouteBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const origin = asString(value.origin) ?? asString(value.from);
  const destination = asString(value.destination) ?? asString(value.to);
  return <BlockShell block={block}><ReadOnlyCard title="路线">
    {!origin && !destination ? null : <>{origin && <CardRow label="起点" value={origin} />}{destination && <CardRow label="终点" value={destination} />}</>}
  </ReadOnlyCard></BlockShell>;
}

export function EventsBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const items = Array.isArray(value.events ?? value.items) ? (value.events ?? value.items) as unknown[] : [];
  const events = items.map((item) => (item && typeof item === "object" ? item as Record<string, unknown> : { raw: item }))
    .map((item) => ({ title: asString(item.title ?? item.name) ?? "事件", time: asString(item.time ?? item.date ?? item.start) }));
  return <BlockShell block={block}><ReadOnlyCard title="事件">
    {events.length === 0 ? null : events.map((event, index) => <CardRow key={index} label={event.time ?? ""} value={event.title} />)}
  </ReadOnlyCard></BlockShell>;
}