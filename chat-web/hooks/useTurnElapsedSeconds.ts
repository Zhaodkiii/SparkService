"use client";

import { useEffect, useState } from "react";

/**
 * CHAT-WEB-027 W3: client-side ticking duration for a running turn's Activity
 * header (1s interval). Only ever computes from the public `started_at`
 * timestamp already in the Canonical Run/TurnSummary projection — never a
 * server push — so it naturally stops mattering once `isRunning` goes false
 * and the caller switches to the server-confirmed `durationMs`.
 */
export function useTurnElapsedSeconds(startedAt: string | null | undefined, isRunning: boolean): number | null {
  const startedMs = startedAt ? Date.parse(startedAt) : NaN;
  const hasStart = Number.isFinite(startedMs);
  const [elapsedMs, setElapsedMs] = useState<number>(() => (hasStart ? Math.max(0, Date.now() - startedMs) : 0));

  useEffect(() => {
    if (!isRunning || !hasStart) return;
    setElapsedMs(Math.max(0, Date.now() - startedMs));
    const interval = setInterval(() => {
      setElapsedMs(Math.max(0, Date.now() - startedMs));
    }, 1000);
    return () => clearInterval(interval);
  }, [isRunning, hasStart, startedMs]);

  if (!hasStart) return null;
  return isRunning ? elapsedMs : null;
}
