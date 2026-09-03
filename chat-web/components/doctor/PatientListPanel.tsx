"use client";

import { useEffect, useState } from "react";
import { Search, Star } from "lucide-react";
import { usePatientWorkspace } from "@/context/PatientWorkspaceContext";
import { PATIENT_QUEUE_LABEL, SERVICE_STATUS_LABEL, patientListTime } from "@/lib/hospital/labels";
import type { PatientQueue } from "@/types/hospital";

const QUEUES = ["all", "priority", "pending", "ended"] as const satisfies readonly PatientQueue[];

/** D-007~D-010：患者列表面板——授权集合内搜索、工作状态筛选、最小工作摘要卡片。 */
export function PatientListPanel() {
  const workspace = usePatientWorkspace();
  const [search, setSearch] = useState(workspace.keyword);

  // 搜索词 300ms 防抖后进入授权集合内查询（D-010：先授权过滤，再搜索）。
  useEffect(() => {
    const timer = window.setTimeout(() => workspace.setKeyword(search.trim()), 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, workspace.setKeyword]);

  return (
    <aside className="patient-list-panel" aria-label="患者列表">
      <label className="sidebar-search patient-list-search">
        <Search size={13} />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="搜索患者姓名或标识…"
          aria-label="搜索患者姓名或标识"
        />
      </label>
      <div className="doctor-queue-tabs patient-queue-tabs" role="tablist" aria-label="患者筛选">
        {QUEUES.map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={workspace.queue === item}
            className="doctor-queue-tab"
            onClick={() => workspace.setQueue(item)}
          >
            <span>{PATIENT_QUEUE_LABEL[item]}</span>
            <em>{workspace.counts[item]}</em>
          </button>
        ))}
      </div>
      {workspace.listError && (
        <p className="sidebar__notice" role="alert">
          {workspace.listError}
          <button type="button" className="doctor-inline-retry" onClick={() => void workspace.reloadList()}>重试</button>
        </p>
      )}
      {workspace.listStatus === "loading" && workspace.patients.length === 0 && (
        <p className="sidebar__notice">正在加载患者…</p>
      )}
      <ul className="patient-card-list">
        {workspace.patients.map((patient) => {
          const selected = workspace.selectedMemberId === patient.member_id;
          return (
            <li key={patient.member_id}>
              <button
                type="button"
                className="patient-card"
                aria-current={selected ? "true" : undefined}
                onClick={() => workspace.selectPatient(patient.member_id)}
              >
                <span className="patient-card__avatar" aria-hidden="true">{(patient.display_name || "患").slice(0, 1)}</span>
                <span className="patient-card__body">
                  <span className="patient-card__title">
                    <strong>{patient.display_name || "未命名患者"}</strong>
                    {patient.priority_patient && (
                      <em className="patient-card__priority"><Star size={11} strokeWidth={2.4} />重点</em>
                    )}
                  </span>
                  <span className="patient-card__meta">{patient.masked_patient_identifier}</span>
                  <span className="patient-card__meta">{patientListTime(patient.latest_conversation_at)}</span>
                </span>
                {patient.service_status && (
                  <span className={`doctor-tag doctor-tag--status-${patient.service_status}`}>
                    {SERVICE_STATUS_LABEL[patient.service_status]}
                  </span>
                )}
              </button>
            </li>
          );
        })}
        {workspace.listStatus === "ready" && workspace.patients.length === 0 && (
          <li className="sidebar__notice">当前条件下暂无患者</li>
        )}
      </ul>
    </aside>
  );
}
