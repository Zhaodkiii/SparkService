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
