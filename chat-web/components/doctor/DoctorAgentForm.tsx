"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentAvatar } from "@/components/doctor/AgentAvatar";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { useAuth } from "@/context/AuthContext";
import { hospitalErrorMessage, isHospitalError } from "@/lib/hospital/errors";
import { AGENT_STATUS_LABEL } from "@/lib/hospital/labels";
import type { DoctorAgentDTO } from "@/types/hospital";

export function DoctorAgentForm() {
  const auth = useAuth();
  const api = useMemo(() => new SparkHospitalApi(auth.client), [auth.client]);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [agent, setAgent] = useState<DoctorAgentDTO | null>(null);
  const [name, setName] = useState("");
  const [publicSummary, setPublicSummary] = useState("");
  const [greeting, setGreeting] = useState("");
  const [serviceBoundary, setServiceBoundary] = useState("");
  const [scenarioBindingId, setScenarioBindingId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const applyAgent = (next: DoctorAgentDTO | null) => {
    setAgent(next);
    if (!next) {
      setStatus("empty");
      return;
    }
    setName(next.name);
    setPublicSummary(next.public_summary);
    setGreeting(next.greeting);
    setServiceBoundary(next.service_boundary);
    setScenarioBindingId(next.scenario_binding_id != null ? String(next.scenario_binding_id) : "");
    setStatus("ready");
  };

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    void api.getAgent()
      .then((data) => { if (!cancelled) applyAgent(data); })
      .catch((cause) => {
        if (cancelled) return;
        setError(hospitalErrorMessage(cause));
        setStatus("error");
      });
    return () => { cancelled = true; };
  }, [api]);

  const payload = () => ({
    name,
    public_summary: publicSummary,
    greeting,
    service_boundary: serviceBoundary,
    department_id: agent?.department?.id,
    scenario_binding_id: scenarioBindingId.trim() ? Number(scenarioBindingId) : undefined,
    version: agent?.version,
  });

  const publishBlockReason = (): string | null => {
    if (!name.trim()) return "请填写公开名称";
    if (!serviceBoundary.trim()) return "请填写服务边界，说明智能体可回答的范围（提交审核必填）";
    const bindingId = scenarioBindingId.trim()
      ? Number(scenarioBindingId)
      : agent?.scenario_binding_id;
    if (!bindingId) return "缺少场景绑定，请联系医院管理员配置后再提交审核";
    if (!agent?.department?.id) return "缺少所属科室，请联系医院管理员配置后再提交审核";
    return null;
  };

  const save = async () => {
    if (!agent) return;
    setBusy(true);
    setError(null);
    try {
      applyAgent(await api.updateAgent(payload()));
    } catch (cause) {
      if (isHospitalError(cause, "AGENT_VERSION_CONFLICT")) {
        try { applyAgent(await api.getAgent()); } catch { /* keep local */ }
      }
      setError(hospitalErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (!agent) return;
    const blockReason = publishBlockReason();
    if (blockReason) {
      setError(blockReason);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await api.updateAgent(payload());
      if (saved.version === undefined) {
        applyAgent(await api.getAgent());
        return;
      }
      applyAgent(await api.submitAgent(saved.version));
    } catch (cause) {
      if (isHospitalError(cause, "AGENT_VERSION_CONFLICT")) {
        try { applyAgent(await api.getAgent()); } catch { /* keep local */ }
      }
      setError(hospitalErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  if (status === "loading") return <section className="doctor-page" aria-busy="true"><p>正在加载智能体资料…</p></section>;
  if (status === "error") {
    return (
      <section className="doctor-page" role="alert">
        <h1>我的智能体</h1>
        <p>{error}</p>
      </section>
    );
  }
  if (status === "empty" || !agent) {
    return (
      <section className="doctor-page">
        <p className="empty-state__eyebrow">我的智能体</p>
        <h1>尚未分配智能体</h1>
        <p>当前医生还没有可维护的医院智能体，请联系医院管理员分配后再编辑公开资料。</p>
      </section>
    );
  }

  const readOnly = agent.publication_status === "review";

  return (
    <section className="doctor-page doctor-agent-page">
      <header className="doctor-page__header">
        <div>
          <p className="empty-state__eyebrow">我的智能体</p>
          <h1>{agent.name || "未命名智能体"}</h1>
          <p>由 {agent.doctor.display_name}{agent.department ? ` / ${agent.department.name}` : ""} 维护</p>
        </div>
        <span className={`doctor-tag doctor-tag--agent-${agent.publication_status}`}>{AGENT_STATUS_LABEL[agent.publication_status]}</span>
      </header>
      <form className="doctor-agent-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <section className="doctor-agent-readonly">
          <h2>智能体头像</h2>
          <div className="doctor-agent-avatar">
            <AgentAvatar
              className="doctor-agent-avatar__image"
              src={agent.avatar_url || ""}
              version={agent.avatar_version || ""}
              name={agent.name}
            />
            <p>{agent.avatar_source === "custom" ? "当前使用智能体专属头像。" : "当前复用医生头像，医生头像更新后自动同步。"}如需更换，请联系医院管理员修改。</p>
          </div>
        </section>
        <label>
          公开名称（必填）
          <input value={name} required disabled={readOnly || busy} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>对外简介<textarea value={publicSummary} disabled={readOnly || busy} onChange={(event) => setPublicSummary(event.target.value)} /></label>
        <label>欢迎语<textarea value={greeting} disabled={readOnly || busy} onChange={(event) => setGreeting(event.target.value)} /></label>
        <label>
          服务边界（提交审核必填）
          <textarea
            value={serviceBoundary}
            required
            disabled={readOnly || busy}
            placeholder="例如：健康信息与就医指导，不提供确诊。"
            onChange={(event) => setServiceBoundary(event.target.value)}
          />
        </label>
        <label>所属科室<input value={agent.department?.name ?? "未指定"} disabled readOnly /></label>
        <label>场景绑定 ID<input value={scenarioBindingId} disabled={readOnly || busy} inputMode="numeric" onChange={(event) => setScenarioBindingId(event.target.value)} /></label>
        <section className="doctor-agent-readonly">
          <h2>绑定知识库（只读）</h2>
          {agent.knowledge_bindings?.length ? (
            <ul>
              {agent.knowledge_bindings.map((item) => (
                <li key={`${item.knowledge_base_id}-${item.usage_scope}`}>{item.knowledge_base_id} · {item.usage_scope} · {item.status}</li>
              ))}
            </ul>
          ) : <p>暂无绑定知识库</p>}
        </section>
        {error ? <p className="doctor-panel-error" role="alert">{error}</p> : null}
        <footer>
          <button type="submit" className="doctor-button doctor-button--ghost" disabled={readOnly || busy}>保存草稿</button>
          <button type="button" className="doctor-button" disabled={busy || agent.publication_status === "review"} onClick={() => void submit()}>提交审核</button>
        </footer>
      </form>
    </section>
  );
}
