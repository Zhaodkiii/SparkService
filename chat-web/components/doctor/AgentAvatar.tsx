"use client";

import { useState } from "react";

/**
 * 统一头像降级状态机（BACKOFFICE-HOSPITAL-AGENT-000002）：
 * remote(agent.avatar_url) → default(统一 AI 默认头像) → initial(名称首字)。
 * avatar_version 变化时重置失败状态并重新加载（渲染期间派生重置，无副作用）。
 */
const DEFAULT_AVATAR =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><rect width="96" height="96" rx="20" fill="#e6f7fb"/><circle cx="48" cy="40" r="16" fill="#00b7d4"/><rect x="24" y="60" width="48" height="20" rx="10" fill="#00b7d4"/><circle cx="42" cy="38" r="3" fill="#fff"/><circle cx="54" cy="38" r="3" fill="#fff"/></svg>',
  );

type Stage = "remote" | "default" | "initial";

export function AgentAvatar({
  src,
  version,
  name,
  className,
}: {
  src?: string | null;
  version?: string | null;
  name?: string | null;
  className?: string;
}) {
  const sourceKey = `${src || ""}|${version || ""}`;
  const [stage, setStage] = useState<Stage>(src ? "remote" : "default");
  const [prevKey, setPrevKey] = useState(sourceKey);

  if (sourceKey !== prevKey) {
    setPrevKey(sourceKey);
    setStage(src ? "remote" : "default");
  }

  const initial = (name || "AI").trim().slice(0, 1).toUpperCase() || "AI";

  return (
    <span className={className} aria-hidden="true">
      {stage === "remote" && src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" onError={() => setStage("default")} />
      ) : stage === "default" ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={DEFAULT_AVATAR} alt="" onError={() => setStage("initial")} />
      ) : (
        initial
      )}
    </span>
  );
}
