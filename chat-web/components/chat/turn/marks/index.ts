import type { ComponentType } from "react";
import type { TurnActivityPhase } from "@/types/chat";
import { ReasoningMark } from "@/components/chat/turn/marks/ReasoningMark";
import { ToolMark } from "@/components/chat/turn/marks/ToolMark";
import { RespondingMark } from "@/components/chat/turn/marks/RespondingMark";
import { RespondedMark } from "@/components/chat/turn/marks/RespondedMark";
import type { MarkProps } from "@/components/chat/turn/marks/MarkSvg";

export { MarkSvg, type MarkProps } from "@/components/chat/turn/marks/MarkSvg";
export { ReasoningMark } from "@/components/chat/turn/marks/ReasoningMark";
export { ToolMark } from "@/components/chat/turn/marks/ToolMark";
export { RespondingMark } from "@/components/chat/turn/marks/RespondingMark";
export { RespondedMark } from "@/components/chat/turn/marks/RespondedMark";

/**
 * CHAT-WEB-027 W3: maps the Sanitized `TurnActivityPhase` (never raw Provider
 * phase strings) to the DeepTutor-derived Mark that best represents it.
 * `composing` uses RespondingMark (writing the final answer); every terminal
 * phase settles on RespondedMark regardless of success/failure — the color
 * distinguishing tone already lives in the surrounding CSS classes.
 */
export function markForPhase(phase: TurnActivityPhase): ComponentType<MarkProps> {
  switch (phase) {
    case "using_tools":
      return ToolMark;
    case "composing":
      return RespondingMark;
    case "completed":
    case "failed":
    case "cancelled":
    case "interrupted":
      return RespondedMark;
    case "exploring":
    case "waiting":
    default:
      return ReasoningMark;
  }
}
