"use client";

import { useRef, useState } from "react";
import { ArrowUp } from "lucide-react";
import { useDoctorAuth } from "@/context/DoctorAuthGate";
import { useDoctorConversations } from "@/context/DoctorConversationsContext";
import { shouldSubmitDoctorMessage } from "@/lib/hospital/composer-keyboard";
import { useAutoSizedTextarea } from "@/lib/use-auto-sized-textarea";
import type { HospitalServiceStatus } from "@/types/hospital";

export function DoctorComposerView({
  serviceStatus,
  doctorLabel,
  busy = false,
  error = null,
  onJoin,
  onSend,
}: {
  serviceStatus: HospitalServiceStatus | null;
  doctorLabel: string;
  busy?: boolean;
  error?: string | null;
  onJoin?: () => Promise<boolean> | boolean;
  onSend?: (text: string) => Promise<boolean> | boolean;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement | null>(null);
  useAutoSizedTextarea(ref, value, 54, 190);

  if (!serviceStatus || serviceStatus === "ai_active") {
    return (
      <div className="composer-shell doctor-composer-state">
        <button type="button" className="doctor-button" disabled={busy || !onJoin} onClick={() => void onJoin?.()}>接管后可回复</button>
        <p className="composer-status">当前由 AI 接待，接管后才能以医生身份回复。</p>
      </div>
    );
  }
  if (serviceStatus === "pending_doctor") {
    return (
      <div className="composer-shell doctor-composer-state">
        <button type="button" className="doctor-button" disabled={busy || !onJoin} onClick={() => void onJoin?.()}>接管并回复</button>
        {error ? <p className="composer-status" role="alert">{error}</p> : <p className="composer-status">接管后即可继续回复该患者。</p>}
      </div>
    );
  }
  if (serviceStatus === "ended") {
    return (
      <div className="composer-shell doctor-composer-state">
        <div className="doctor-ended-banner">本次服务已结束，历史消息仍可查看，不能继续回复。</div>
        {error ? <p className="composer-status" role="alert">{error}</p> : null}
      </div>
    );
  }

  const submit = async () => {
    const text = value.trim();
    if (!text || busy) return;
    const accepted = await onSend?.(text);
    if (accepted) setValue("");
  };

  return (
    <div className="composer-shell">
      <p className="doctor-composer-identity">以“{doctorLabel} · 真人医生”身份回复</p>
      <div className="composer" aria-label="医生回复编辑器">
        <textarea
          ref={ref}
          value={value}
          disabled={busy}
          aria-label="医生回复"
          placeholder="输入回复内容…"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (shouldSubmitDoctorMessage(event)) {
              event.preventDefault();
              void submit();
            }
          }}
        />
        <div className="composer__footer">
          <p className="doctor-composer-hint">Enter 换行 · Cmd/Ctrl + Enter 发送</p>
          <button className="send-button" type="button" aria-label="发送" onClick={() => void submit()} disabled={!value.trim() || busy}>
            <ArrowUp size={18} strokeWidth={2.2} />
          </button>
        </div>
      </div>
      <div className="composer-status" aria-live="polite">{error || "医生回复会直接发给患者，不会触发 AI 生成。"}</div>
    </div>
  );
}

export function DoctorComposer() {
  const { doctor } = useDoctorAuth();
  const conversations = useDoctorConversations();
  const status = conversations.detail?.service_status ?? null;
  return (
    <DoctorComposerView
      serviceStatus={status}
      doctorLabel={doctor.display_name}
      busy={conversations.writeBusy}
      error={conversations.writeError}
      onJoin={conversations.join}
      onSend={conversations.sendMessage}
    />
  );
}
