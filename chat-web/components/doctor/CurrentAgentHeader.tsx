"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Pencil, RefreshCw, X } from "lucide-react";
import { DoctorAgentForm } from "@/components/doctor/DoctorAgentForm";
import { useAuth } from "@/context/AuthContext";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { hospitalErrorMessage } from "@/lib/hospital/errors";
import { AGENT_STATUS_LABEL } from "@/lib/hospital/labels";
import { useDoctorAuth } from "@/context/DoctorAuthGate";
import type { DoctorAgentDTO } from "@/types/hospital";

export function CurrentAgentHeader() {
  const auth = useAuth();
  const { doctor } = useDoctorAuth();
  const api = useMemo(() => new SparkHospitalApi(auth.client), [auth.client]);
  const [agent, setAgent] = useState<DoctorAgentDTO | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);

  const load = useCallback(() => {
    setStatus("loading");
    setError(null);
    void api.getAgent()
      .then((data) => {
        setAgent(data);
        setStatus(data ? "ready" : "empty");
      })
      .catch((cause) => {
        setStatus("error");
        setError(hospitalErrorMessage(cause));
      });
  }, [api]);

  useEffect(() => {
    if (auth.status !== "authenticated") return;
    queueMicrotask(load);
  }, [auth.status, doctor.id, load]);

  const initials = (agent?.name || doctor.display_name || "AI").slice(0, 1);
  const knowledgeCount = agent?.knowledge_bindings?.filter((item) => item.status === "active").length ?? 0;

  return (
    <section className="current-agent-header" aria-label="当前服务智能体">
      <div className="current-agent-header__title">当前服务智能体</div>
      {status === "loading" && <div className="current-agent-header__state" aria-busy="true">正在加载智能体信息…</div>}
      {status === "error" && (
        <div className="current-agent-header__state current-agent-header__state--error" role="alert">
          智能体信息加载失败，患者工作台其他内容仍可正常使用。<button type="button" className="doctor-inline-retry" onClick={load}><RefreshCw size={13} />重试</button>
        </div>
      )}
      {status === "empty" && <div className="current-agent-header__state">当前医生尚未分配智能体。</div>}
      {status === "ready" && agent && (
        <div className="current-agent-header__content">
          <span className="current-agent-header__avatar" aria-hidden="true">
            {agent.doctor.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={agent.doctor.avatar_url} alt="" />
            ) : initials}
          </span>
          <div className="current-agent-header__identity">
            <div className="current-agent-header__name-row">
              <strong>{agent.name || "未命名智能体"}</strong>
              <span className="doctor-tag">医生智能体</span>
              <span className={`doctor-tag doctor-tag--agent-${agent.publication_status}`}>{AGENT_STATUS_LABEL[agent.publication_status]}</span>
            </div>
            <p>{agent.doctor.display_name} · {agent.doctor.title || "未填写职称"} · {agent.department?.name || "未指定科室"}</p>
            <p className="current-agent-header__summary">{agent.public_summary || "暂无对外简介"}</p>
          </div>
          <span className="current-agent-header__knowledge">已关联知识库 {knowledgeCount} 个</span>
          <button type="button" className="doctor-button doctor-button--ghost current-agent-header__edit" onClick={() => setEditorOpen(true)}>
            <Pencil size={13} />编辑智能体
          </button>
        </div>
      )}
      {editorOpen && agent && (
        <div className="current-agent-dialog" role="presentation">
          <button type="button" className="current-agent-dialog__scrim" aria-label="关闭编辑智能体" onClick={() => setEditorOpen(false)} />
          <section className="current-agent-dialog__panel" role="dialog" aria-modal="true" aria-labelledby="current-agent-dialog-title">
            <header className="current-agent-dialog__head">
              <div>
                <h2 id="current-agent-dialog-title">编辑医生智能体</h2>
                <p>{agent.name} · {agent.doctor.display_name} / {agent.department?.name || "未指定科室"}</p>
              </div>
              <button type="button" className="doctor-icon-button" aria-label="关闭编辑智能体" onClick={() => setEditorOpen(false)}><X size={17} /></button>
            </header>
            <div className="current-agent-dialog__body">
              <DoctorAgentForm />
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
