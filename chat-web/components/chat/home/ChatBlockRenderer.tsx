"use client";

import type { ChatBlockDTO } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";
import type { HealthResourceReference } from "@/types/medical-resource";
import { renderBlock } from "@/components/chat/blocks/registry";

/**
 * Block renderer entry point. Delegates to the kind registry so structured
 * cards from iOS render correctly, isolated per-card behind an error boundary.
 */
export function ChatBlockRenderer({ block, activity, onHealthResourceOpen }: {
  block: ChatBlockDTO;
  activity?: ToolActivityDTO | null;
  onHealthResourceOpen?: (reference: HealthResourceReference) => void;
}) {
  return <>{renderBlock({ block, activity, onHealthResourceOpen })}</>;
}
