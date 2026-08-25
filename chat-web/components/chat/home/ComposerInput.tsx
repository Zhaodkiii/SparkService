"use client";

import { useRef } from "react";
import { useAutoSizedTextarea } from "@/lib/use-auto-sized-textarea";
import { shouldSubmitOnEnter } from "@/lib/composer-keyboard";

export function ComposerInput({ value, onChange, onSubmit, disabled = false }: { value: string; onChange: (value: string) => void; onSubmit: () => void; disabled?: boolean }) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  useAutoSizedTextarea(ref, value);
  return <textarea ref={ref} value={value} disabled={disabled} aria-label="输入消息" placeholder="向小鲸健康提问…" onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (shouldSubmitOnEnter(event)) { event.preventDefault(); onSubmit(); } }} />;
}
