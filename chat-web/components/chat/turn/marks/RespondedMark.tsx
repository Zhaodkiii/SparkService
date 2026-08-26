/**
 * CHAT-WEB-027 W3: extracted from DeepTutor Web
 * `web/components/chat/home/TracePanels.tsx` (source commit
 * 684d615393322cd18d9edb3a85eacb3beba0d811, Apache-2.0), lines ~1899-1916.
 * See `chat-web/THIRD_PARTY_NOTICES.md` for the full attribution entry.
 *
 * Responded — a settled, slightly softer mark: a compact 4-ray bloom with a
 * filled inner dot, conveying "thought captured, complete".
 */
import { MarkSvg, type MarkProps } from "@/components/chat/turn/marks/MarkSvg";

export function RespondedMark(props: MarkProps) {
  return (
    <MarkSvg {...props}>
      <g transform="rotate(8 12 12)">
        <circle cx="12" cy="12" r="1.8" fill="currentColor" stroke="none" />
        <path d="M12 4.5 L12 8" />
        <path d="M12 19.5 L12 16" />
        <path d="M4.5 12 L8 12" />
        <path d="M19.5 12 L16 12" />
        <path d="M6 6 L8.6 8.6" />
        <path d="M18 18 L15.4 15.4" />
      </g>
    </MarkSvg>
  );
}
