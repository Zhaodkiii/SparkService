/**
 * CHAT-WEB-027 W3: extracted from DeepTutor Web
 * `web/components/chat/home/TracePanels.tsx` (source commit
 * 684d615393322cd18d9edb3a85eacb3beba0d811, Apache-2.0), lines ~1881-1892.
 * See `chat-web/THIRD_PARTY_NOTICES.md` for the full attribution entry.
 *
 * Responding — a flowing ink-stroke that swoops up to the right, terminating
 * in a small dot, like a quill marking paper.
 */
import { MarkSvg, type MarkProps } from "@/components/chat/turn/marks/MarkSvg";

export function RespondingMark(props: MarkProps) {
  return (
    <MarkSvg {...props}>
      <path d="M3 18 Q 8 7 14 11 T 21 6.5" />
      <circle cx="21" cy="6.5" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="5.5" cy="20.5" r="0.9" fill="currentColor" stroke="none" />
    </MarkSvg>
  );
}
