"use client";

import type { ChatBlockDTO } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";
import { renderBlock } from "@/components/chat/blocks/registry";

/**
 * Block renderer entry point. Delegates to the kind registry so structured
 * cards from iOS render correctly, isolated per-card behind an error boundary.
 */
export function ChatBlockRenderer({ block, activity }: { block: ChatBlockDTO; activity?: ToolActivityDTO | null }) {
  return <>{renderBlock({ block, activity })}</>;
}