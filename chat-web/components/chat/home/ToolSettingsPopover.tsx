"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Lock, RefreshCw, SlidersHorizontal, Wrench } from "lucide-react";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalThreads } from "@/context/ThreadContext";
import { SparkToolCatalogApi } from "@/lib/api/tool-catalog-api";
import { SparkApiError } from "@/lib/api/http-client";
import type { ToolCatalogDTO, ToolUnavailableReason } from "@/types/tool";

const UNAVAILABLE_COPY: Record<ToolUnavailableReason, string> = {
  feature_disabled: "当前环境暂未开启",
  model_unsupported: "当前模型不支持工具调用",
  member_required: "需要先选择成员",
  source_required: "需要先附加健康资料",
};

type LoadState = "loading" | "ready" | "error";

/**
 * P4 tool settings entry: per-thread allowlist of read-only server tools.
 * Toggles PATCH the thread preferences with an If-Match revision; a 409
 * conflict refetches the catalog once instead of failing silently.
 */
export function ToolSettingsPopover() {
  const auth = useOptionalAuth();
  const threads = useOptionalThreads();
  const threadId = threads?.selectedThreadId ?? null;
  const [open, setOpen] = useState(false);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [catalog, setCatalog] = useState<ToolCatalogDTO | null>(null);
  const [pendingTool, setPendingTool] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const api = useMemo(() => (auth ? new SparkToolCatalogApi(auth.client) : null), [auth]);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const load = useCallback(async () => {
    if (!api || !threadId) return;
    setLoadState("loading");
    setError(null);
    try {
      setCatalog(await api.catalog(threadId));
      setLoadState("ready");
    } catch {
      setLoadState("error");
      setError("无法加载工具设置，请稍后重试");
    }
  }, [api, threadId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const toggle = async (name: string, nextEnabled: boolean) => {
    if (!api || !threadId || !catalog || pendingTool) return;
    setPendingTool(name);
    setNotice(null);
    setError(null);
    const enabledTools = catalog.tools.filter((tool) => (tool.name === name ? nextEnabled : tool.enabled)).map((tool) => tool.name);
    // Keep catalog order stable for the persisted allowlist.
    const ordered = catalog.tools.filter((tool) => enabledTools.includes(tool.name)).map((tool) => tool.name);
    try {
      await api.updateEnabledTools(threadId, ordered, catalog.preferences_revision);
      await load();
      setNotice(nextEnabled ? "已开启，下一轮对话生效" : "已关闭，下一轮对话生效");
    } catch (cause) {
      const conflict = cause instanceof SparkApiError && cause.failure.messageKey === "chat_preferences_revision_conflict";
      if (conflict) {
        await load();
        setNotice("设置已同步为最新状态，请重试");
      } else {
        setError("保存失败，请稍后重试");
      }
    } finally {
      setPendingTool(null);
    }
  };

  const anyAvailable = catalog?.tools.some((tool) => tool.available) ?? false;

  return <div className="tool-settings" ref={rootRef}>
    <button className="composer-icon" type="button" aria-label="工具设置" aria-expanded={open} title="服务端工具设置（允许 AI 按需使用，非每次必然调用）" disabled={!threadId} onClick={() => setOpen((value) => !value)}><SlidersHorizontal size={16} /></button>
    {open && (
      <div className="tool-settings__popover" role="dialog" aria-label="服务端工具设置">
        <header>
          <span><Wrench size={13} /> 服务端工具</span>
          <button type="button" aria-label="刷新" onClick={() => void load()}><RefreshCw size={13} /></button>
        </header>
        {loadState === "loading" && <p className="tool-settings__hint">正在加载可用工具…</p>}
        {loadState === "error" && <p className="tool-settings__hint tool-settings__hint--error">{error ?? "加载失败"}</p>}
        {loadState === "ready" && catalog && (
          <>
            {!anyAvailable && <p className="tool-settings__hint">当前对话暂无可用工具。选择成员或附加健康资料后，AI 可以按需读取已授权的信息。</p>}
            <ul>
              {catalog.tools.map((tool) => (
                <li key={tool.name} className={tool.available ? "" : "tool-settings__item--unavailable"}>
                  <div>
                    <strong>{tool.display_name}</strong>
                    <span>{tool.available ? tool.description : UNAVAILABLE_COPY[tool.unavailable_reason ?? "feature_disabled"]}</span>
                  </div>
                  {tool.available ? (
                    <button
                      type="button"
                      role="switch"
                      aria-checked={tool.enabled}
                      aria-label={`${tool.enabled ? "关闭" : "开启"}${tool.display_name}`}
                      className={`tool-settings__switch${tool.enabled ? " tool-settings__switch--on" : ""}`}
                      disabled={pendingTool === tool.name}
                      onClick={() => void toggle(tool.name, !tool.enabled)}
                    ><span /></button>
                  ) : (
                    <span className="tool-settings__lock" title={UNAVAILABLE_COPY[tool.unavailable_reason ?? "feature_disabled"]}><Lock size={13} /></span>
                  )}
                </li>
              ))}
            </ul>
            {notice && <p className="tool-settings__notice">{notice}</p>}
            {error && <p className="tool-settings__hint tool-settings__hint--error">{error}</p>}
            <footer>开关表示允许 AI 在需要时使用，不代表每轮必然调用。所有工具均为只读；调用过程会显示在会话活动里，原始数据不会展示，设置仅对下一轮回答生效。</footer>
          </>
        )}
      </div>
    )}
  </div>;
}
