"use client";

import { ChevronRight, Plus, RefreshCw, Star } from "lucide-react";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { usePatientWorkspace } from "@/context/PatientWorkspaceContext";
import type { PatientCacheModule } from "@/lib/hospital/patient-cache";
import {
  GENDER_LABEL,
  RISK_LABEL,
  SERVICE_STATUS_LABEL,
  formatClock,
  lifestyleLabel,
  patientListTime,
  relativeTime,
} from "@/lib/hospital/labels";
import type { PatientMedicalSafetyDTO, PatientWorkspaceDTO } from "@/types/hospital";

function CacheNote({ cachedAt, stale }: { cachedAt: string | null; stale: boolean }) {
  if (!cachedAt) return null;
  return <span className="patient-module__cache">缓存 {formatClock(cachedAt)}{stale ? " · 已过期，后台刷新中" : ""}</span>;
}

function ModuleError({ error, module }: { error: string; module: PatientCacheModule }) {
  const workspace = usePatientWorkspace();
  return (
    <p className="patient-module__error" role="alert">
      {error}
      <button type="button" className="doctor-inline-retry" onClick={() => workspace.retryModule(module)}>重试</button>
    </p>
  );
}

function ProfileRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <p className="patient-profile-row">
      <span>{label}</span>
      <em>{value && value.trim() ? value : "未填写"}</em>
    </p>
  );
}

function SafetyList({ label, items }: { label: string; items: string[] }) {
  return (
    <p className="patient-profile-row patient-profile-row--block">
      <span>{label}</span>
      <em>{items.length ? items.join("、") : "暂无已记录"}</em>
    </p>
  );
}

/** D-004/D-006：患者身份头部 + 只读基础资料三分区。 */
function PatientIdentityAndProfile({ profile }: { profile: PatientWorkspaceDTO }) {
  const { patient, basic_profile: basic, health_profile: health, medical_safety: safety } = profile;
  const safetyMap: Array<[string, string[]]> = [
    ["过敏史", (safety as PatientMedicalSafetyDTO).allergies],
    ["长期用药", safety.long_term_medications],
    ["既往病史", safety.past_medical_history],
  ];
  return (
    <>
      <section className="patient-identity" aria-label="患者身份">
        <span className="patient-identity__avatar" aria-hidden="true">
          {patient.avatar_url
            // eslint-disable-next-line @next/next/no-img-element
            ? <img src={patient.avatar_url} alt="" />
            : (patient.display_name || "患").slice(0, 1)}
        </span>
        <div className="patient-identity__main">
          <h1>
            {patient.display_name || "未命名患者"}
            <span className="patient-identity__sub">
              {GENDER_LABEL[patient.gender] ?? patient.gender ?? "未填写"}
              {patient.age !== null ? ` · ${patient.age}岁` : ""}
            </span>
          </h1>
          <p>患者编号：{patient.patient_number || "未生成"}</p>
        </div>
        <div className="patient-identity__tags">
          {patient.service_status
            ? <span className={`doctor-tag doctor-tag--status-${patient.service_status}`}>{SERVICE_STATUS_LABEL[patient.service_status]}</span>
            : <span className="doctor-tag">暂无会话</span>}
          {patient.priority_patient && <span className="patient-tag-priority"><Star size={11} strokeWidth={2.4} />重点患者</span>}
        </div>
      </section>

      <section className="patient-section" aria-label="患者基础资料">
        <header className="patient-section__head">
          <h2>基础资料（只读）</h2>
        </header>
        <div className="patient-profile-grid">
          <div className="patient-profile-col">
            <h3>基本信息</h3>
            <ProfileRow label="手机" value={basic.phone_masked} />
            <ProfileRow label="证件" value={basic.identity_number_masked} />
            <ProfileRow label="地区" value={basic.region} />
            <ProfileRow label="职业" value={basic.occupation} />
            <ProfileRow label="婚姻" value={basic.marital_status} />
          </div>
          <div className="patient-profile-col">
            <h3>健康档案</h3>
            <ProfileRow label="身高" value={health.height_cm !== null ? `${health.height_cm} cm` : null} />
            <ProfileRow label="体重" value={health.weight_kg !== null ? `${health.weight_kg} kg` : null} />
            <ProfileRow label="BMI" value={health.bmi !== null ? String(health.bmi) : null} />
            <ProfileRow label="血型" value={health.blood_type ? `${health.blood_type} 型` : null} />
            <ProfileRow label="吸烟/饮酒" value={`${lifestyleLabel(health.smoking_status)} / ${lifestyleLabel(health.drinking_status)}`} />
          </div>
          <div className="patient-profile-col">
            <h3>医疗安全信息</h3>
            {safetyMap.map(([label, items]) => <SafetyList key={label} label={label} items={items} />)}
          </div>
        </div>
      </section>
    </>
  );
}

/** D-012~D-014/D-019：患者会话列表 + 新建对话；点击行打开右侧会话抽屉。 */
function PatientConversationsSection() {
  const workspace = usePatientWorkspace();
  const conversationsCtx = useOptionalDoctorConversations();
  const conversationsModule = workspace.conversations;
  const items = conversationsModule.data ?? [];

  return (
    <section className="patient-section" aria-label="患者会话">
      <header className="patient-section__head">
        <h2>患者会话（当前医生有权查看）</h2>
        <div className="patient-section__actions">
          <CacheNote cachedAt={conversationsModule.cachedAt} stale={conversationsModule.stale} />
          <button
            type="button"
            className="doctor-button patient-button-primary"
            disabled={workspace.actionBusy}
            onClick={() => void workspace.createConversation()}
          >
            <Plus size={14} strokeWidth={2.2} />新建对话
          </button>
        </div>
      </header>
      {conversationsModule.error && <ModuleError error={conversationsModule.error} module="conversations" />}
      {workspace.actionError && <p className="patient-module__error" role="alert">{workspace.actionError}</p>}
      {conversationsModule.status === "loading" && !items.length && <p className="patient-module__hint">正在加载会话…</p>}
      {conversationsModule.status === "ready" && !items.length && !conversationsModule.error && (
        <p className="patient-module__hint">暂无可查看会话，可点击“新建对话”发起咨询。</p>
      )}
      {items.length > 0 && (
        <ul className="patient-conversation-list">
          {items.map((card) => {
            const open = conversationsCtx?.selectedThreadId === card.thread_id;
            const fresh = !open && (conversationsCtx?.newMessageThreadIds.includes(card.thread_id) ?? false);
            return (
              <li key={card.thread_id}>
                <button
                  type="button"
                  className="patient-conversation-row"
                  aria-current={open ? "true" : undefined}
                  onClick={() => conversationsCtx?.selectConversation(card.thread_id)}
                >
                  <span className="patient-conversation-row__title">
                    {card.agent.name}
                    {fresh && <i className="doctor-card__fresh" role="img" aria-label="新消息" title="新消息" />}
                  </span>
                  <span className="patient-conversation-row__tags">
                    {card.doctor_attention_level === "priority" && (
                      <em className="patient-card__priority"><Star size={11} strokeWidth={2.4} />重点</em>
                    )}
                    <span className={`doctor-tag doctor-tag--status-${card.service_status}`}>{SERVICE_STATUS_LABEL[card.service_status]}</span>
                  </span>
                  <span className="patient-conversation-row__time">最近更新 {patientListTime(card.updated_at)}</span>
                  <ChevronRight size={15} className="patient-conversation-row__chevron" aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** D-020~D-023：AI 总结（系统生成）——医生主动生成/刷新，正文只读，可标记已了解。 */
function PatientSummarySection() {
  const workspace = usePatientWorkspace();
  const summaryModule = workspace.summary;
  const summary = summaryModule.data;

  return (
    <section className="patient-section" aria-label="AI 总结">
      <header className="patient-section__head">
        <h2>AI 总结（系统生成）</h2>
        <div className="patient-section__actions">
          {summary?.acknowledged && <span className="patient-tag-ack">已了解</span>}
          {summary && (
            <button
              type="button"
              className="doctor-button doctor-button--ghost patient-button-inline"
              disabled={workspace.actionBusy}
              onClick={() => void workspace.setSummaryAcknowledged(!summary.acknowledged)}
            >
              {summary.acknowledged ? "取消已了解" : "已了解"}
            </button>
          )}
          <button
            type="button"
            className="doctor-button patient-button-primary patient-button-inline"
            disabled={workspace.actionBusy}
            onClick={() => void workspace.generateSummary()}
          >
            <RefreshCw size={13} strokeWidth={2.2} />{summary ? "生成/刷新" : "生成总结"}
          </button>
        </div>
      </header>
      {summaryModule.error && <ModuleError error={summaryModule.error} module="summary" />}
      {summaryModule.status === "loading" && !summary && <p className="patient-module__hint">正在生成 AI 总结…</p>}
      {!summary && summaryModule.status === "ready" && !summaryModule.error && (
        <p className="patient-module__hint">尚未生成 AI 总结。点击“生成总结”后基于当前可见患者资料与会话生成。</p>
      )}
      {summary && (
        <div className="patient-summary">
          <div className="patient-summary__grid">
            <div>
              <h3>当前问题/服务概况</h3>
              <p>{summary.sections.current_issues || "暂无内容"}</p>
            </div>
            <div>
              <h3>关键健康信息</h3>
              <p>{summary.sections.key_health_info || "暂无内容"}</p>
            </div>
            <div>
              <h3>会话要点</h3>
              <p>{summary.sections.conversation_highlights || "暂无内容"}</p>
            </div>
          </div>
          <div className="patient-summary__follow">
            <h3>待跟进事项</h3>
            {summary.sections.follow_up_items.length
              ? <ul>{summary.sections.follow_up_items.map((item) => <li key={item}>{item}</li>)}</ul>
              : <p>暂无待跟进事项</p>}
          </div>
          <footer className="patient-summary__meta">
            <span>
              {summary.system_generated ? "系统生成" : "医生生成"} · v{summary.version} · 生成时间 {formatClock(summary.generated_at) || relativeTime(summary.generated_at)}
            </span>
            <CacheNote cachedAt={summaryModule.cachedAt} stale={summaryModule.stale} />
          </footer>
        </div>
      )}
    </section>
  );
}

/** D-024~D-026：风险卡片只读视图；人工调整进入现有风险工具流程，不在本页改级。 */
function PatientRiskSection() {
  const workspace = usePatientWorkspace();
  const conversationsCtx = useOptionalDoctorConversations();
  const riskModule = workspace.risk;
  const risk = riskModule.data;

  return (
    <section className="patient-section" aria-label="风险评估">
      <header className="patient-section__head">
        <h2>风险评估（现有风险工具）</h2>
        <div className="patient-section__actions">
          <CacheNote cachedAt={riskModule.cachedAt} stale={riskModule.stale} />
          {risk?.source_thread_id && (
            <button
              type="button"
              className="doctor-button doctor-button--ghost patient-button-inline"
              onClick={() => conversationsCtx?.selectConversation(risk.source_thread_id)}
            >
              查看详情
            </button>
          )}
          <button
            type="button"
            className="doctor-button doctor-button--ghost patient-button-inline"
            disabled={riskModule.status === "loading"}
            onClick={() => void workspace.refreshRisk()}
          >
            <RefreshCw size={13} strokeWidth={2.2} />刷新
          </button>
        </div>
      </header>
      {riskModule.error && <ModuleError error={riskModule.error} module="risk" />}
      {riskModule.status === "loading" && !risk && <p className="patient-module__hint">正在加载风险结果…</p>}
      {!risk && riskModule.status === "ready" && !riskModule.error && (
        <p className="patient-module__hint">暂无风险评估结果。</p>
      )}
      {risk && (
        <div className="patient-risk">
          <span className={`doctor-tag patient-risk__level doctor-tag--risk-${risk.level}`}>{RISK_LABEL[risk.level]}</span>
          <div className="patient-risk__body">
            <p>结果状态：{risk.status || "未知"} · 更新时间 {relativeTime(risk.updated_at) || "未知"}</p>
            {risk.suggestion ? <p>处理建议:{risk.suggestion}</p> : null}
            <p className="patient-risk__note">风险等级与医生关注是两套独立标签；人工调整请进入现有风险工具流程。</p>
          </div>
        </div>
      )}
    </section>
  );
}

function PatientProfileModule() {
  const workspace = usePatientWorkspace();
  const profileModule = workspace.profile;
  return (
    <>
      {profileModule.error && !profileModule.data && (
        <section className="patient-section"><ModuleError error={profileModule.error} module="profile" /></section>
      )}
      {profileModule.status === "loading" && !profileModule.data && (
        <section className="patient-section"><p className="patient-module__hint">正在加载患者资料…</p></section>
      )}
      {profileModule.data && (
        <>
          <div className="patient-module__cache-row"><CacheNote cachedAt={profileModule.cachedAt} stale={profileModule.stale} />{profileModule.error && <ModuleError error={profileModule.error} module="profile" />}</div>
          <PatientIdentityAndProfile profile={profileModule.data} />
        </>
      )}
    </>
  );
}

/** D-028：患者工作台主区——身份头部 → 基础资料 → 会话列表 → AI 总结 → 风险评估。 */
export function PatientWorkspaceMain() {
  const workspace = usePatientWorkspace();

  if (workspace.selectedMemberId === null) {
    return (
      <main className="patient-main" aria-label="患者工作台">
        <div className="empty-state">
          <div>
            <p className="empty-state__eyebrow">患者工作台</p>
            <h1>选择一位患者</h1>
            <p>从左侧患者列表选择患者后，查看基础资料、患者会话、AI 总结与风险评估。</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="patient-main" aria-label="患者工作台">
      <PatientProfileModule />
      <PatientSummarySection />
      <PatientRiskSection />
      <PatientConversationsSection />
    </main>
  );
}
