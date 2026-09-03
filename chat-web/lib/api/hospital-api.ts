import type { SparkHttpClient } from "@/lib/api/http-client";
import { normalizeMessageBlocks } from "@/lib/chat/message-normalizer";
import type { WebSocketTicketData } from "@/types/run";
import type {
  ConversationDetailDTO,
  ConversationListDTO,
  ConversationMessagesDTO,
  ConversationQueue,
  DoctorAgentDTO,
  DoctorAgentUpdatePayload,
  DoctorAttentionLevel,
  DoctorMessageDTO,
  DoctorSendMessageDTO,
  DoctorWorkspaceDTO,
  PatientConversationsDTO,
  PatientListDTO,
  PatientQueue,
  PatientRiskCardDTO,
  PatientSummaryDTO,
  PatientWorkspaceDTO,
  StaffMeDTO,
  WorkLogListDTO,
} from "@/types/hospital";

function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== undefined && value !== "") params.set(key, String(value));
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

function withIdempotency(key: string, extra?: HeadersInit): HeadersInit {
  return { "Idempotency-Key": key, ...extra };
}

export class SparkHospitalApi {
  constructor(private readonly http: SparkHttpClient) {}

  getMe(): Promise<StaffMeDTO> {
    return this.http.requestOrThrow("GET", "/api/hospital/v1/me/");
  }

  getWorkspace(): Promise<DoctorWorkspaceDTO> {
    return this.http.requestOrThrow("GET", "/api/hospital/v1/me/workspace/");
  }

  getAgent(): Promise<DoctorAgentDTO | null> {
    return this.http.requestOrThrow("GET", "/api/hospital/v1/me/agent/");
  }

  updateAgent(payload: DoctorAgentUpdatePayload): Promise<DoctorAgentDTO> {
    return this.http.requestOrThrow("PATCH", "/api/hospital/v1/me/agent/", { body: payload });
  }

  submitAgent(version: number): Promise<DoctorAgentDTO> {
    return this.http.requestOrThrow("POST", "/api/hospital/v1/me/agent/submit/", { body: { version } });
  }

  listConversations(params: { queue?: ConversationQueue; keyword?: string; page?: number; page_size?: number } = {}): Promise<ConversationListDTO> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/conversations/${query({
      queue: params.queue ?? "all",
      keyword: params.keyword,
      page: params.page ?? 1,
      page_size: params.page_size ?? 50,
    })}`);
  }

  getConversation(threadId: string): Promise<ConversationDetailDTO> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/conversations/${threadId}/`);
  }

  async getMessages(threadId: string): Promise<ConversationMessagesDTO> {
    const data = await this.http.requestOrThrow<ConversationMessagesDTO>("GET", `/api/hospital/v1/doctor/conversations/${threadId}/messages/`);
    return {
      items: data.items.map((message) => ({
        ...message,
        blocks: normalizeMessageBlocks(message.blocks ?? []),
      })),
    };
  }

  sendMessage(threadId: string, payload: { text: string; version?: number }, idempotencyKey: string): Promise<DoctorSendMessageDTO> {
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/conversations/${threadId}/messages/`, {
      body: payload,
      headers: withIdempotency(idempotencyKey),
    });
  }

  join(threadId: string, version: number, idempotencyKey: string): Promise<ConversationDetailDTO> {
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/conversations/${threadId}/join/`, {
      body: { version },
      headers: withIdempotency(idempotencyKey),
    });
  }

  /** DOCTOR-WORKSPACE-000001 D-015/D-016：取消接管，恢复 AI 自动回复。 */
  leave(threadId: string, version: number, idempotencyKey: string): Promise<ConversationDetailDTO> {
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/conversations/${threadId}/leave/`, {
      body: { version },
      headers: withIdempotency(idempotencyKey),
    });
  }

  updateAttention(
    threadId: string,
    payload: { doctor_attention_level: DoctorAttentionLevel; attention_note?: string; version: number },
    idempotencyKey: string,
  ): Promise<ConversationDetailDTO> {
    return this.http.requestOrThrow("PATCH", `/api/hospital/v1/doctor/conversations/${threadId}/attention/`, {
      body: payload,
      headers: withIdempotency(idempotencyKey),
    });
  }

  endConversation(threadId: string, payload: { version: number; end_reason: string }, idempotencyKey: string): Promise<ConversationDetailDTO> {
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/conversations/${threadId}/end/`, {
      body: payload,
      headers: withIdempotency(idempotencyKey),
    });
  }

  getWorkLogs(params: { page?: number; page_size?: number } = {}): Promise<WorkLogListDTO> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/me/work-logs/${query({
      page: params.page ?? 1,
      page_size: params.page_size ?? 50,
    })}`);
  }

  /** BACKOFFICE-CONVERSATION-000002：医生会话实时通道一次性 ticket。 */
  createConversationWebSocketTicket(): Promise<WebSocketTicketData> {
    return this.http.requestOrThrow("POST", "/api/hospital/v1/doctor/conversations/ws-tickets/");
  }

  /* ---------- DOCTOR-WORKSPACE-000001 患者工作台 ---------- */

  /** D-007~D-010：患者列表（授权集合内搜索/筛选/排序）。 */
  listPatients(params: { queue?: PatientQueue; keyword?: string; page?: number; page_size?: number } = {}): Promise<PatientListDTO> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/patients/${query({
      queue: params.queue ?? "all",
      keyword: params.keyword,
      page: params.page ?? 1,
      page_size: params.page_size ?? 50,
    })}`);
  }

  /** D-004/D-006：患者工作台只读聚合快照。 */
  getPatientWorkspace(memberId: number): Promise<PatientWorkspaceDTO> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/patients/${memberId}/workspace/`);
  }

  /** D-012/D-013：患者会话列表。 */
  getPatientConversations(memberId: number): Promise<PatientConversationsDTO> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/patients/${memberId}/conversations/`);
  }

  /** D-019：新建咨询，继承当前患者与当前医生智能体上下文。 */
  createPatientConversation(memberId: number, idempotencyKey: string): Promise<ConversationDetailDTO> {
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/patients/${memberId}/conversations/`, {
      body: {},
      headers: withIdempotency(idempotencyKey),
    });
  }

  /** D-020/D-023：最新 AI 总结只读查询（不触发生成）。 */
  getPatientSummary(memberId: number): Promise<PatientSummaryDTO | null> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/patients/${memberId}/summary/`);
  }

  /** D-020：医生主动生成/刷新 AI 总结。 */
  generatePatientSummary(memberId: number, idempotencyKey: string): Promise<PatientSummaryDTO> {
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/patients/${memberId}/summary/generate/`, {
      body: {},
      headers: withIdempotency(idempotencyKey),
    });
  }

  /** D-023：标记/取消“已了解”（天然幂等，update_or_create）。 */
  ackPatientSummary(memberId: number, acknowledged: boolean): Promise<PatientSummaryDTO> {
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/patients/${memberId}/summary/ack/`, {
      body: { acknowledged },
    });
  }

  /** D-024~D-026：风险卡片只读查看。 */
  getPatientRisk(memberId: number): Promise<PatientRiskCardDTO | null> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/patients/${memberId}/risk/`);
  }
}

export function toLocalDoctorMessage(sent: DoctorSendMessageDTO, text: string): DoctorMessageDTO {
  return {
    thread_id: sent.thread_id,
    role: "assistant",
    client_message_id: sent.client_message_id,
    server_message_id: sent.server_message_id,
    delivery_state: "sent",
    created_at: sent.created_at,
    actor_type: "doctor",
    sender: sent.sender,
    blocks: [{
      id: sent.client_message_id,
      kind: "text",
      status: "ready",
      revision: 1,
      order_key: 1,
      node_role: "timeline",
      payload: { text: { _0: text } },
    }],
  };
}
