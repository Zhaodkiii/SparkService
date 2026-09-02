"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { useAuth } from "@/context/AuthContext";
import { hospitalErrorMessage } from "@/lib/hospital/errors";
import { WORK_LOG_ACTION_LABEL } from "@/lib/hospital/labels";
import type { WorkLogEntryDTO } from "@/types/hospital";

type RangeFilter = "today" | "week" | "all";

function startOfToday() {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

function matchesRange(item: WorkLogEntryDTO, range: RangeFilter) {
  if (range === "all") return true;
  const created = Date.parse(item.created_at);
  if (!Number.isFinite(created)) return false;
  if (range === "today") return created >= startOfToday();
  return created >= startOfToday() - 6 * 86_400_000;
}

export function DoctorWorkLogList() {
  const auth = useAuth();
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [items, setItems] = useState<WorkLogEntryDTO[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<RangeFilter>("week");
  const [action, setAction] = useState("all");
  const [keyword, setKeyword] = useState("");

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    void new SparkHospitalApi(auth.client).getWorkLogs({ page: 1, page_size: 50 })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setStatus("ready");
      })
      .catch((cause) => {
        if (cancelled) return;
        setError(hospitalErrorMessage(cause));
        setStatus("error");
      });
    return () => { cancelled = true; };
  }, [auth.client]);

  const actions = useMemo(() => Array.from(new Set(items.map((item) => item.action))), [items]);
  const filtered = items.filter((item) => {
    if (!matchesRange(item, range)) return false;
    if (action !== "all" && item.action !== action) return false;
    if (keyword.trim() && !item.resource_id.toLowerCase().includes(keyword.trim().toLowerCase())) return false;
    return true;
  });

  return (
    <section className="doctor-page doctor-worklog-page">
      <header className="doctor-page__header">
        <div>
          <p className="empty-state__eyebrow">工作记录</p>
          <h1>本人操作摘要</h1>
          <p>只读审计结果，不能修改或删除。</p>
        </div>
      </header>
      <div className="doctor-worklog-filters">
        {(["today", "week", "all"] as const).map((item) => (
          <button key={item} type="button" className="doctor-queue-tab" aria-selected={range === item} onClick={() => setRange(item)}>
            {item === "today" ? "今天" : item === "week" ? "近 7 天" : "全部"}
          </button>
        ))}
        <select value={action} aria-label="动作类型" onChange={(event) => setAction(event.target.value)}>
          <option value="all">全部动作</option>
          {actions.map((item) => <option key={item} value={item}>{WORK_LOG_ACTION_LABEL[item] || item}</option>)}
        </select>
        <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索会话号" aria-label="搜索会话号" />
      </div>
      {status === "loading" && <p>正在加载工作记录…</p>}
      {status === "error" && <p className="doctor-panel-error" role="alert">{error}</p>}
      {status === "ready" && !filtered.length && <p className="doctor-panel-muted">当前筛选没有工作记录。</p>}
      <ul className="doctor-worklog-list">
        {filtered.map((item) => (
          <li key={item.id}>
            <time>{new Date(item.created_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time>
            <strong>{WORK_LOG_ACTION_LABEL[item.action] || item.action}</strong>
            <span>{item.resource_id}</span>
            {item.resource_type.includes("conversation") || item.resource_type.includes("thread") || item.resource_type === "hospital_conversation" || item.resource_type === "hospital_message" ? (
              <Link href={`/doctor/conversations/${encodeURIComponent(item.resource_id)}` as never}>查看对应会话</Link>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
