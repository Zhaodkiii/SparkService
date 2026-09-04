import type { ChatMessageWireDTO } from "@/types/sync";

export type HospitalServiceStatus = "ai_active" | "pending_doctor" | "doctor_joined" | "ended";
export type DoctorAttentionLevel = "normal" | "follow_up" | "priority";
export type RiskSignalLevel = "none" | "low" | "medium" | "high";
export type AgentPublicationStatus = "draft" | "review" | "published" | "disabled";
export type ConversationQueue = "all" | "pending" | "priority" | "ended" | "active";
export type HospitalActorType = "patient" | "ai_agent" | "doctor" | "system";

export interface HospitalPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface HospitalPublicDTO {
  id: string;
  code: string;
  name: string;
  short_name: string;
  grade: string;
  address: string;
  service_phone: string;
  emergency_phone: string;
  website_url: string;
  introduction: string;
  service_mode: string;
  status: string;
  province_code: string;
  city_code: string;
  district_code: string;
}

export interface DepartmentPublicDTO {
  id: string;
  hospital_id: string;
  parent_id: string | null;
  code: string;
  name: string;
  short_name: string;
  description: string;
  sort_order: number;
  status: string;
  doctor_count?: number | null;
  agent_count?: number | null;
}

export interface DoctorPublicDTO {
  id: string;
  display_name: string;
  title: string;
  specialties: string[];
  introduction: string;
  license_status: string;
  profile_status: string;
  avatar_url?: string;
}

export interface StaffMembershipDTO {
  id: string;
  role: string;
  status: string;
  employee_no: string;
}

export interface StaffMeDTO {
  hospital: HospitalPublicDTO;
  membership: StaffMembershipDTO;
  doctor: DoctorPublicDTO | null;
}

export interface DoctorWorkspaceDTO {
  doctor: { id: string; display_name: string; title: string };
  hospital: { id: string; name: string };
  counts: ConversationQueueCounts;
}

export interface ConversationQueueCounts {
  all: number;
  pending: number;
  priority: number;
  ended: number;
}

export interface ConversationAgentSummary {
  id: string;
  name: string;
  publication_status: AgentPublicationStatus;
}

export interface ConversationCardDTO {
  thread_id: string;
  hospital: HospitalPublicDTO;
  department: DepartmentPublicDTO;
  doctor: DoctorPublicDTO;
  agent: ConversationAgentSummary;
  member_id: number | null;
  patient_display_name: string;
  service_status: HospitalServiceStatus;
  doctor_attention_level: DoctorAttentionLevel;
  risk_signal_level: RiskSignalLevel;
  assigned_at: string | null;
  doctor_joined_at: string | null;
  ended_at: string | null;
  end_reason: string;
  attention_note?: string;
  version: number;
  updated_at: string;
  title: string;
  unread_count: number;
}

export type ConversationDetailDTO = ConversationCardDTO;

export interface DoctorSenderSnapshot {
  actor_type?: HospitalActorType;
  actor_id?: string;
  display_name?: string;
  avatar_url?: string;
  source?: string;
  doctor?: {
    doctor_id: string;
    display_name: string;
    title: string;
    hospital_name: string;
    department_name: string;
    avatar_url: string;
    verified: boolean;
  };
  agent?: {
    agent_id: string;
    display_name: string;
    is_ai: boolean;
  };
}

export interface DoctorMessageDTO extends ChatMessageWireDTO {
  actor_type?: HospitalActorType | null;
  sender?: DoctorSenderSnapshot;
}

export interface ConversationListDTO {
  items: ConversationCardDTO[];
  pagination: HospitalPagination;
  counts: ConversationQueueCounts;
}

export interface ConversationMessagesDTO {
  items: DoctorMessageDTO[];
}

export interface DoctorSendMessageDTO {
  message_id: number;
  server_message_id: string;
  client_message_id: string;
  thread_id: string;
  role: string;
  created_at: string;
  sender: DoctorSenderSnapshot;
  version: number;
}

export interface AgentKnowledgeBindingDTO {
  knowledge_base_id: string;
  usage_scope: string;
  status: string;
  sort_order: number;
}

export interface DoctorAgentDTO {
  id: string;
  hospital_id: string;
  department: DepartmentPublicDTO | null;
  doctor: DoctorPublicDTO;
  name: string;
  public_summary: string;
  greeting: string;
  service_boundary: string;
  publication_status: AgentPublicationStatus;
  published_at: string | null;
  avatar_source?: "doctor" | "custom";
  avatar_url?: string;
  avatar_version?: string;
  scenario_binding_id?: number | null;
  doctor_editable_policy?: Record<string, unknown>;
  version?: number;
  knowledge_bindings?: AgentKnowledgeBindingDTO[];
}

export interface DoctorAgentUpdatePayload {
  name?: string;
  public_summary?: string;
  greeting?: string;
  service_boundary?: string;
  department_id?: string;
  scenario_binding_id?: number;
  version?: number;
}

export interface WorkLogEntryDTO {
  id: number;
  action: string;
  resource_type: string;
  resource_id: string;
  created_at: string;
  request_id: string;
}

export interface WorkLogListDTO {
  items: WorkLogEntryDTO[];
  pagination: HospitalPagination;
}

/** BACKOFFICE-CONVERSATION-000002：医生工作台实时事件契约（payload_version 1）。
 *  事件只携带会话变化提示，不包含消息正文。 */
export interface HospitalConversationUpdatedEvent {
  type: "hospital.conversation.updated";
  payload_version?: number;
  event_id?: string;
  thread_id: string;
  message_ids?: string[];
  cursor?: string;
  emitted_at?: string;
  change_kind?: string;
}

/* ---------- DOCTOR-WORKSPACE-000001 患者工作台 ---------- */

export type PatientQueue = "all" | "priority" | "pending" | "ended";

/** D-008：患者列表卡片最小工作摘要。 */
export interface PatientCardDTO {
  member_id: number;
  display_name: string;
  masked_patient_identifier: string;
  service_status: HospitalServiceStatus | null;
  latest_conversation_at: string | null;
  priority_patient: boolean;
  available_conversation_count: number;
}

export interface PatientListDTO {
  items: PatientCardDTO[];
  pagination: HospitalPagination;
  counts: ConversationQueueCounts;
}

export interface PatientIdentityDTO {
  member_id: number;
  display_name: string;
  gender: string;
  birth_date: string | null;
  age: number | null;
  patient_number: string;
  avatar_url: string;
  service_status: HospitalServiceStatus | null;
  priority_patient: boolean;
}

/** D-004：基础身份分区；null 表示“未填写”。 */
export interface PatientBasicProfileDTO {
  phone_masked: string | null;
  identity_number_masked: string | null;
  region: string | null;
  occupation: string | null;
  marital_status: string | null;
}

/** D-004：健康档案分区；null 表示“未填写”。 */
export interface PatientHealthProfileDTO {
  height_cm: number | null;
  weight_kg: number | null;
  bmi: number | null;
  blood_type: string | null;
  smoking_status: string | null;
  drinking_status: string | null;
}

/** D-004：医疗安全信息分区；空数组表示“已查询但无记录”。 */
export interface PatientMedicalSafetyDTO {
  allergies: string[];
  long_term_medications: string[];
  past_medical_history: string[];
}

/** D-006：患者工作台只读聚合快照。 */
export interface PatientWorkspaceDTO {
  patient: PatientIdentityDTO;
  basic_profile: PatientBasicProfileDTO;
  health_profile: PatientHealthProfileDTO;
  medical_safety: PatientMedicalSafetyDTO;
  work_flags: { priority_patient: boolean };
  freshness: {
    member_updated_at: string | null;
    health_profile_updated_at: string | null;
    snapshot_at: string | null;
  };
}

export interface PatientConversationsDTO {
  items: ConversationCardDTO[];
}

/** D-020~D-023：AI 总结只读快照。 */
export interface PatientSummaryDTO {
  id: string;
  version: number;
  status: string;
  system_generated: boolean;
  sections: {
    current_issues: string;
    key_health_info: string;
    conversation_highlights: string;
    follow_up_items: string[];
  };
  data_scope: {
    thread_count: number;
    profile_updated_at: string | null;
    conversation_cutoff_at: string | null;
  };
  tool_name: string;
  generated_at: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
}

/** D-024~D-026：风险卡片只读视图（复用现有风险工具信号）。 */
export interface PatientRiskCardDTO {
  level: RiskSignalLevel;
  status: string;
  suggestion: string;
  source_thread_id: string;
  updated_at: string;
  data_cutoff_at: string;
  source: string;
}
