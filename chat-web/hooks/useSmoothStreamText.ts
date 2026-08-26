"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Direct migration from DeepTutor Web `web/hooks/useSmoothStreamText.ts`
 * (source commit 684d615393322cd18d9edb3a85eacb3beba0d811, Apache-2.0). Pure
 * React hook with no DeepTutor data-model dependency; logic is unchanged.
 * See `chat-web/THIRD_PARTY_NOTICES.md` for the full attribution entry.
 *
 * Separates "network receive speed" from "visual reveal speed": the Reducer
 * still holds the full canonical text immediately, this hook only controls
 * how much of it is painted per animation frame.
 */
interface SmoothStreamOptions {
  maxCharsPerFrame?: number;
  minCharsPerFrame?: number;
  catchUpDivisor?: number;
  enabled?: boolean;
}

export function useSmoothStreamText(
  content: string,
  isStreaming: boolean,
  options: SmoothStreamOptions = {},
): string {
  const {
    maxCharsPerFrame = 120,
    minCharsPerFrame = 2,
    catchUpDivisor = 5,
    enabled = true,
  } = options;

  const [shown, setShown] = useState<string>(content);
  const shownLenRef = useRef<number>(content.length);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (!enabled) {
      if (shownLenRef.current !== content.length || shown !== content) {
        shownLenRef.current = content.length;
        setShown(content);
      }
      return;
    }

    if (!isStreaming) {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = 0;
      }
      if (shownLenRef.current !== content.length || shown !== content) {
        shownLenRef.current = content.length;
        setShown(content);
      }
      return;
    }

    if (shownLenRef.current > content.length) {
      shownLenRef.current = content.length;
      setShown(content);
      return;
    }

    if (shownLenRef.current >= content.length) {
      return;
    }

    const step = () => {
      rafRef.current = 0;
      const target = content.length;
      const current = shownLenRef.current;
      if (current >= target) return;
      const backlog = target - current;
      const advance = Math.min(
        maxCharsPerFrame,
        Math.max(minCharsPerFrame, Math.ceil(backlog / catchUpDivisor)),
      );
      const next = Math.min(target, current + advance);
      shownLenRef.current = next;
      setShown(content.slice(0, next));
      if (next < target) {
        rafRef.current = requestAnimationFrame(step);
      }
    };

    if (!rafRef.current) {
      rafRef.current = requestAnimationFrame(step);
    }

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = 0;
      }
    };
  }, [content, isStreaming, enabled, maxCharsPerFrame, minCharsPerFrame, catchUpDivisor]);

  return shown;
}
