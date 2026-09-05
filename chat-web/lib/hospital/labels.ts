import type {
  AgentPublicationStatus,
  ConversationCardDTO,
  ConversationEndReasonCode,
  ConversationQueue,
  DoctorAttentionLevel,
  HospitalActorType,
  HospitalServiceStatus,
  PatientQueue,
  RiskSignalLevel,
} from "@/types/hospital";

export const SERVICE_STATUS_LABEL: Record<HospitalServiceStatus, string> = {
  ai_active: "AI 服务中",
  pending_doctor: "待接诊",
  doctor_joined: "问诊中",
  ended: "已结束",
};

export const ATTENTION_LABEL: Record<DoctorAttentionLevel, string> = {
  normal: "普通",
  follow_up: "随访",
  priority: "重点",
};

export const RISK_LABEL: Record<RiskSignalLevel, string> = {
  none: "无风险信号",
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};

export const QUEUE_LABEL: Record<ConversationQueue, string> = {
  all: "全部",
  pending: "待接诊",
  joined: "问诊中",
  priority: "重点",
  ended: "已结束",
  active: "进行中",
};

export const AGENT_STATUS_LABEL: Record<AgentPublicationStatus, string> = {
  draft: "草稿",
  review: "待审核",
  published: "已发布",
  disabled: "已暂停",
};

export const WORK_LOG_ACTION_LABEL: Record<string, string> = {
  "hospital.conversation.join": "接管问诊",
  "hospital.conversation.leave": "取消接管",
  "hospital.conversation.attention_update": "标记关注",
  "hospital.conversation.end": "结束问诊",
  "hospital.conversation.risk_update": "调整风险",
  "hospital.doctor_message.send": "回复患者",
};

/* ---------- DOCTOR-WORKSPACE-000001 患者工作台 ---------- */

/** D-010：患者列表工作状态筛选标签（全部/重点/待接诊/问诊中/已结束）。 */
export const PATIENT_QUEUE_LABEL: Record<PatientQueue, string> = {
  all: "全部",
  priority: "重点",
  pending: "待接诊",
  active: "问诊中",
  ended: "已结束",
};

export const GENDER_LABEL: Record<string, string> = {
  male: "男",
  female: "女",
  unknown: "未填写",
};

/** 吸烟/饮酒等生活方式原始值 → 展示文案；未知值原样展示。 */
export const LIFESTYLE_STATUS_LABEL: Record<string, string> = {
  never: "从不",
  none: "无",
  occasional: "偶尔",
  current: "持续",
  regular: "规律",
  daily: "每日",
  quit: "已戒",
  unknown: "未填写",
};

export function lifestyleLabel(value: string | null | undefined): string {
  if (!value) return "未填写";
  return LIFESTYLE_STATUS_LABEL[value] ?? value;
}

/** 患者列表最近会话时间：今天 HH:mm / 昨天 HH:mm / MM-DD HH:mm。 */
export function patientListTime(value?: string | null): string {
  if (!value) return "暂无会话";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return "暂无会话";
  const date = new Date(parsed);
  const now = new Date();
  const clock = date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const dayDelta = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (dayDelta <= 0) return `今天 ${clock}`;
  if (dayDelta === 1) return `昨天 ${clock}`;
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${clock}`;
}

/** DOCTOR-WORKSPACE-000004 第 28 问：固定结束原因枚举（与服务端 ConversationEndReason 一致）。 */
export const END_REASON_OPTIONS: ReadonlyArray<{ value: ConversationEndReasonCode; label: string }> = [
  { value: "resolved", label: "已完成咨询" },
  { value: "offline_referral", label: "建议线下就诊" },
  { value: "patient_no_followup", label: "患者无继续咨询" },
  { value: "other", label: "其他" },
] as const;

export function endReasonLabel(detail: Pick<ConversationCardDTO, "end_reason" | "end_reason_code" | "end_reason_note">): string {
  if (detail.end_reason) return detail.end_reason;
  const option = END_REASON_OPTIONS.find((item) => item.value === detail.end_reason_code);
  if (!option) return "";
  return detail.end_reason_code === "other" && detail.end_reason_note ? `其他：${detail.end_reason_note}` : option.label;
}

export function actorPrefix(actorType: HospitalActorType | null | undefined, senderName?: string): string {
  if (actorType === "patient") return "患者：";
  if (actorType === "ai_agent") return "AI：";
  if (actorType === "doctor") return `${senderName || "医生"}：`;
  if (actorType === "system") return "系统：";
  return "";
}

export function relativeTime(value?: string | null): string {
  if (!value) return "";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return "";
  const delta = Date.now() - parsed;
  if (delta < 60_000) return "刚刚";
  if (delta < 3_600_000) return `${Math.floor(delta / 60_000)} 分钟前`;
  if (delta < 86_400_000) return `${Math.floor(delta / 3_600_000)} 小时前`;
  if (delta < 172_800_000) return "昨天";
  return new Date(parsed).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export function formatClock(value?: string | null): string {
  if (!value) return "";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return "";
  return new Date(parsed).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}
