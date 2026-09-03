"use client";

import { type RefObject, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { inferActorType } from "@/lib/hospital/message-text";
import { doctorMessageStableKey, sliceAppendedMessages } from "@/lib/hospital/realtime";
import type { DoctorMessageDTO } from "@/types/hospital";

/** BACKOFFICE-CONVERSATION-000002 Q4/§8.3.4：距底 ≤48px 视为“跟随状态”。 */
const BOTTOM_THRESHOLD_PX = 48;

/** BACKOFFICE-CONVERSATION-000002 Q4：当前会话消息区滚动策略。
 *
 *  - 首轮内容与切换会话后钉到底部展示最新。
 *  - 跟随状态下消息更新自动滚到底部；定向拉取合并的多条消息只触发一次滚动。
 *  - 医生向上阅读历史时保持位置，按追加条数聚合“有 N 条新消息”按钮；
 *    点击按钮或自行滚回底部后清零计数并恢复跟随。
 *  - 医生主动发送（追加中出现医生身份消息）视为回到底部。
 *  - 完整快照替换（锚点丢失）不计入未查看数量，也不强行跳动。
 */
export function useDoctorMessageFollow(
  rootRef: RefObject<HTMLElement | null>,
  messages: DoctorMessageDTO[],
  threadId: string | null,
) {
  const [unseenCount, setUnseenCount] = useState(0);
  const followRef = useRef(true);
  const unseenRef = useRef(0);
  const lastKeyRef = useRef<string | null>(null);

  const setUnseen = useCallback((value: number) => {
    unseenRef.current = value;
    setUnseenCount(value);
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const root = rootRef.current;
    if (root) root.scrollTo({ top: root.scrollHeight, behavior });
  }, [rootRef]);

  // 切换会话：重置跟随与未查看计数，等待首轮内容渲染后由下方 effect 钉底。
  useLayoutEffect(() => {
    followRef.current = true;
    lastKeyRef.current = null;
    if (unseenRef.current) setUnseen(0);
  }, [setUnseen, threadId]);

  // 消息更新：把一次定向拉取/合并视为一轮，一轮最多一次滚动决策。
  useLayoutEffect(() => {
    if (!messages.length) {
      lastKeyRef.current = null;
      return;
    }
    const previousKey = lastKeyRef.current;
    lastKeyRef.current = doctorMessageStableKey(messages[messages.length - 1]);
    if (previousKey === null) {
      // 首轮内容：钉到底部展示最新。
      followRef.current = true;
      scrollToBottom();
      return;
    }
    const appended = sliceAppendedMessages(previousKey, messages);
    if (appended.some((item) => inferActorType(item) === "doctor")) {
      // 医生主动发送后视为回到底部。
      followRef.current = true;
      if (unseenRef.current) setUnseen(0);
      scrollToBottom();
      return;
    }
    if (followRef.current) {
      scrollToBottom();
      return;
    }
    if (appended.length) setUnseen(unseenRef.current + appended.length);
  }, [messages, scrollToBottom, setUnseen]);

  // 滚动监听与内容高度变化：距底 ≤48px 恢复跟随并清零未查看；跟随状态下内容撑高继续钉底。
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const onScroll = () => {
      const atBottom = root.scrollHeight - root.scrollTop - root.clientHeight <= BOTTOM_THRESHOLD_PX;
      followRef.current = atBottom;
      if (atBottom && unseenRef.current) setUnseen(0);
    };
    const observer = new MutationObserver(() => {
      if (followRef.current) scrollToBottom();
    });
    observer.observe(root, { childList: true, subtree: true, characterData: true });
    root.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => {
      observer.disconnect();
      root.removeEventListener("scroll", onScroll);
    };
  }, [rootRef, scrollToBottom, setUnseen]);

  const jumpToLatest = useCallback(() => {
    followRef.current = true;
    setUnseen(0);
    scrollToBottom("smooth");
  }, [scrollToBottom, setUnseen]);

  return { unseenCount, showNewMessages: unseenCount > 0, jumpToLatest };
}
