"use client";

import { Wrench } from "lucide-react";
import { asString, BlockShell, blockValueObject, ReadOnlyCard, UnsupportedBlock } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";
import { ToolActivityDisclosure } from "@/components/chat/home/ToolActivityDisclosure";
import { CHAT_TOOL_UI_ENABLED } from "@/lib/feature-flags";

/** Legacy Web-internal tool projection kinds (`toolCall` / `toolResult`). */
export function ToolActivityBlock({ block, activity }: BlockRenderProps) {
  if (!CHAT_TOOL_UI_ENABLED) return <UnsupportedBlock block={block} />;
  return <ToolActivityDisclosure block={block} activity={activity ?? null} />;
}

/** iOS `tool` block: server tool presentation with no live activity projection. */
export function ToolBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const name = asString(value.name) ?? asString(value.display_name) ?? "服务端工具";
  const result = asString(value.content) ?? asString(value.result_preview);
  return <BlockShell block={block}><ReadOnlyCard title={name}><Wrench size={14} />{result && <p>{result}</p>}</ReadOnlyCard></BlockShell>;
}