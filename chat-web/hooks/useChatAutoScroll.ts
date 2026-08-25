"use client";

import { type RefObject, useCallback, useEffect, useLayoutEffect, useRef } from "react";

/**
 * Adapted from DeepTutor Web's pin-to-bottom implementation. The Spark
 * version accepts the existing scroll root instead of owning a ref, and
 * follows Spark Run block revisions rather than DeepTutor session state.
 * It intentionally never exposes or stores hidden model reasoning.
 */
export function useChatAutoScroll(rootRef: RefObject<HTMLElement | null>, dependency: unknown) {
  const followRef = useRef(true);
  const pin = useCallback(() => { const root = rootRef.current; if (root && followRef.current) root.scrollTop = root.scrollHeight; }, [rootRef]);
  useLayoutEffect(() => { pin(); }, [dependency, pin]);
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    let frame = 0;
    const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; pin(); }); };
    const onScroll = () => { followRef.current = root.scrollHeight - root.scrollTop - root.clientHeight < 96; };
    const onWheel = (event: WheelEvent) => { if (event.deltaY < 0) followRef.current = false; };
    const observer = new MutationObserver(schedule);
    observer.observe(root, { childList: true, subtree: true, characterData: true });
    root.addEventListener("scroll", onScroll, { passive: true });
    root.addEventListener("wheel", onWheel, { passive: true });
    root.addEventListener("load", schedule, true);
    schedule();
    return () => { observer.disconnect(); root.removeEventListener("scroll", onScroll); root.removeEventListener("wheel", onWheel); root.removeEventListener("load", schedule, true); if (frame) cancelAnimationFrame(frame); };
  }, [pin, rootRef]);
}
