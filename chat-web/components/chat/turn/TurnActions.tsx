"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { Check, Clipboard, RefreshCcw, ThumbsDown, ThumbsUp, Trash2, Volume2 } from "lucide-react";

interface TurnActionsProps {
  text: string;
  onRegenerate?: () => void;
  onDelete?: () => void;
  onFeedback?: (value: "up" | "down") => void;
}

function canSpeak(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
}

const noopSubscribe = () => () => {};

/**
 * 回合操作（能力五）：复制、朗读、重新生成、删除、反馈。
 * 朗读使用浏览器 SpeechSynthesis，内容不上传；不支持时隐藏。
 */
export function TurnActions({ text, onRegenerate, onDelete, onFeedback }: TurnActionsProps) {
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const speakable = useSyncExternalStore(noopSubscribe, canSpeak, () => false);

  useEffect(() => () => { if (canSpeak()) window.speechSynthesis.cancel(); }, []);

  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  const speak = () => {
    if (!canSpeak()) return;
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  };

  return <div className="message-actions">
    <button type="button" aria-label="复制回答" title="复制回答" disabled={!text} onClick={() => void copy()}>{copied ? <Check size={14} /> : <Clipboard size={14} />}</button>
    {speakable && <button type="button" aria-label={speaking ? "停止朗读" : "朗读"} title={speaking ? "停止朗读" : "朗读"} disabled={!text} onClick={speak}>{speaking ? <span className="message-actions__stop">■</span> : <Volume2 size={14} />}</button>}
    <button type="button" aria-label="有帮助" title="有帮助" disabled={!onFeedback} onClick={() => onFeedback?.("up")}><ThumbsUp size={14} /></button>
    <button type="button" aria-label="没有帮助" title="没有帮助" disabled={!onFeedback} onClick={() => onFeedback?.("down")}><ThumbsDown size={14} /></button>
    {onRegenerate && <button type="button" aria-label="重新生成" title="重新生成" onClick={onRegenerate}><RefreshCcw size={14} /></button>}
    {onDelete && <button type="button" aria-label="删除回合" title="删除回合" onClick={onDelete}><Trash2 size={14} /></button>}
  </div>;
}