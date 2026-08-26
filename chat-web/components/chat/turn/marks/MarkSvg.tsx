/**
 * CHAT-WEB-027 W3: extracted from DeepTutor Web
 * `web/components/chat/home/TracePanels.tsx` (source commit
 * 684d615393322cd18d9edb3a85eacb3beba0d811, Apache-2.0), lines ~1805-1827.
 * Pure presentational SVG wrapper; no DeepTutor data model attached. See
 * `chat-web/THIRD_PARTY_NOTICES.md` for the full attribution entry.
 */
import type { ReactNode } from "react";

export type MarkProps = {
  size?: number;
  className?: string;
  strokeWidth?: number;
};

export function MarkSvg({ size = 16, className, strokeWidth = 1.5, children }: MarkProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}
