"use client";

import { useLayoutEffect, type RefObject } from "react";

export function useAutoSizedTextarea(ref: RefObject<HTMLTextAreaElement | null>, value: string, min = 28, max = 200): void {
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    node.style.height = "0px";
    node.style.height = `${Math.min(Math.max(node.scrollHeight, min), max)}px`;
    node.style.overflowY = node.scrollHeight > max ? "auto" : "hidden";
  }, [ref, value, min, max]);
}
