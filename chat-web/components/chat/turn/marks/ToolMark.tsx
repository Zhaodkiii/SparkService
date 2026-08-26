/**
 * CHAT-WEB-027 W3: extracted from DeepTutor Web
 * `web/components/chat/home/TracePanels.tsx` (source commit
 * 684d615393322cd18d9edb3a85eacb3beba0d811, Apache-2.0), lines ~1860-1874.
 * See `chat-web/THIRD_PARTY_NOTICES.md` for the full attribution entry.
 *
 * Tool using — an off-axis orbital motif: a soft elliptical orbit arc with a
 * small filled satellite riding it and two stray sparks.
 */
import { MarkSvg, type MarkProps } from "@/components/chat/turn/marks/MarkSvg";

export function ToolMark(props: MarkProps) {
  return (
    <MarkSvg {...props}>
      <circle cx="12" cy="13" r="2.4" />
      <path d="M3.5 9.5 A 10.5 8 -18 0 1 20.5 14" />
      <circle cx="20.5" cy="14" r="1.5" fill="currentColor" stroke="none" />
      <path d="M5 19 L7.2 17.5" />
      <path d="M18 4 L19.5 6" />
    </MarkSvg>
  );
}
