/**
 * CHAT-WEB-027 W3: extracted from DeepTutor Web
 * `web/components/chat/home/TracePanels.tsx` (source commit
 * 684d615393322cd18d9edb3a85eacb3beba0d811, Apache-2.0), lines ~1829-1853.
 * See `chat-web/THIRD_PARTY_NOTICES.md` for the full attribution entry.
 *
 * Reasoning — asymmetric 12-ray radial burst, tilted ~12° so it reads as
 * hand-sketched rather than geometric.
 */
import { MarkSvg, type MarkProps } from "@/components/chat/turn/marks/MarkSvg";

export function ReasoningMark(props: MarkProps) {
  return (
    <MarkSvg {...props}>
      <g transform="rotate(12 12 12)">
        <path d="M12 2 L12 7.5" />
        <path d="M12 22 L12 16.5" />
        <path d="M2 12 L7.5 12" />
        <path d="M22 12 L16.5 12" />
        <path d="M4.6 4.6 L8.4 8.4" />
        <path d="M19.4 19.4 L15.6 15.6" />
        <path d="M4.2 19.8 L8.2 15.8" />
        <path d="M19.8 4.2 L15.8 8.2" />
        <path d="M7.6 2.3 L9 5.8" />
        <path d="M16.4 2.3 L15 5.8" />
        <path d="M7.6 21.7 L9 18.2" />
        <path d="M16.4 21.7 L15 18.2" />
      </g>
    </MarkSvg>
  );
}
