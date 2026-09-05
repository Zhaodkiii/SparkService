import type { SparkHttpClient } from "@/lib/api/http-client";
import { normalizeMessageBlocks } from "@/lib/chat/message-normalizer";
import type { ReadyImagePayload } from "@/lib/chat/image-drafts";
import type { DoctorAttachmentPayload } from "@/lib/hospital/attachments";
import type { WebSocketTicketData } from "@/types/run";
import type {
  ConsultRecordsDTO,
  ConversationAttachmentItemDTO,
  ConversationAttachmentUploadDTO,
  ConversationDetailDTO,
  ConversationEndReasonCode,
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
  ReadCursorResultDTO,
  RiskHistoryDTO,
  RiskSignalLevel,
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

  /** DOCTOR-WORKSPACE-000004 第 34 问：首屏最近一页；before 游标向上加载更早消息。 */
  async getMessages(threadId: string, params: { before?: string; limit?: number } = {}): Promise<ConversationMessagesDTO> {
    const data = await this.http.requestOrThrow<ConversationMessagesDTO>(
      "GET",
      `/api/hospital/v1/doctor/conversations/${threadId}/messages/${query({ before: params.before, limit: params.limit })}`,
    );
    return {
      ...data,
      items: data.items.map((message) => ({
        ...message,
        blocks: normalizeMessageBlocks(message.blocks ?? []),
      })),
    };
  }

  sendMessage(threadId: string, payload: DoctorSendMessagePayload, idempotencyKey: string): Promise<DoctorSendMessageDTO> {
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

  /** DOCTOR-WORKSPACE-000004 第 28 问：结束原因固定枚举 + 可选补充说明。 */
  endConversation(
    threadId: string,
    payload: { version: number; end_reason_code: ConversationEndReasonCode; end_reason_note?: string },
    idempotencyKey: string,
  ): Promise<ConversationDetailDTO> {
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/conversations/${threadId}/end/`, {
      body: payload,
      headers: withIdempotency(idempotencyKey),
    });
  }

  /** DOCTOR-WORKSPACE-000004 第 24/25 问：医生人工调整风险等级（理由可选）。 */
  updateRisk(
    threadId: string,
    payload: { risk_signal_level: RiskSignalLevel; reason?: string; version: number },
    idempotencyKey: string,
  ): Promise<ConversationDetailDTO> {
    return this.http.requestOrThrow("PATCH", `/api/hospital/v1/doctor/conversations/${threadId}/risk/`, {
      body: payload,
      headers: withIdempotency(idempotencyKey),
    });
  }

  /** DOCTOR-WORKSPACE-000004 第 26 问：当前问诊风险调整历史。 */
  getRiskHistory(threadId: string, params: { page?: number; page_size?: number } = {}): Promise<RiskHistoryDTO> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/conversations/${threadId}/risk-history/${query({
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
    })}`);
  }

  /** DOCTOR-WORKSPACE-000004 第 20/31 问：消息加载成功后推进已读游标。 */
  markReadCursor(threadId: string, lastReadMessageId?: number): Promise<ReadCursorResultDTO> {
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/conversations/${threadId}/read-cursor/`, {
      body: lastReadMessageId ? { last_read_message_id: lastReadMessageId } : {},
    });
  }

  /** DOCTOR-WORKSPACE-000004 第 16 问：医生上传当前问诊附件（PDF/JPG/PNG）。 */
  uploadConversationAttachment(threadId: string, file: File): Promise<ConversationAttachmentUploadDTO> {
    const form = new FormData();
    form.append("file", file, file.name);
    return this.http.requestOrThrow("POST", `/api/hospital/v1/doctor/conversations/${threadId}/attachments/`, {
      rawBody: form,
    });
  }

  /** DOCTOR-WORKSPACE-000004：当前问诊病历与附件清单（只读）。 */
  getConversationAttachments(threadId: string): Promise<{ items: ConversationAttachmentItemDTO[] }> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/conversations/${threadId}/attachments/`);
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

  /* ---------- DOCTOR-WORKSPACE-000004 独立线上问诊工作台 ---------- */

  /** 问诊患者列表：仅包含患者客户端已提交线上问诊的患者。 */
  listConsultPatients(params: { queue?: PatientQueue; keyword?: string; page?: number; page_size?: number } = {}): Promise<PatientListDTO> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/consults/patients/${query({
      queue: params.queue ?? "all",
      keyword: params.keyword,
      page: params.page ?? 1,
      page_size: params.page_size ?? 50,
    })}`);
  }

  /** 某患者名下的线上问诊记录（含问诊编号与主诉）。 */
  getConsultRecords(memberId: number): Promise<ConsultRecordsDTO> {
    return this.http.requestOrThrow("GET", `/api/hospital/v1/doctor/consults/patients/${memberId}/records/`);
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

/** 医生发送消息请求体（attachments 携带图片/文档 file_id，数量上限由服务端配置）。 */
export interface DoctorSendMessagePayload {
  text: string;
  version?: number;
  attachments?: Array<{
    file_id: string;
    type?: "image" | "document";
    order?: number;
    mime_type?: string;
    file_size?: number;
    display_url?: string;
  }>;
}

export function toLocalDoctorMessage(
  sent: DoctorSendMessageDTO,
  text: string,
  images: ReadyImagePayload[] = [],
  documents: DoctorAttachmentPayload[] = [],
): DoctorMessageDTO {
  const blocks: DoctorMessageDTO["blocks"] = [];
  if (text) {
    blocks.push({
      id: sent.client_message_id,
      kind: "text",
      status: "ready",
      revision: 1,
      order_key: 1000,
      node_role: "timeline",
      payload: { text: { _0: text } },
    });
  }
  const localImages: ReadyImagePayload[] = [
    ...images,
    ...documents
      .filter((document) => document.type === "image")
      .map((document, index) => ({
        fileId: String(document.file_id),
        fileUuid: document.file_uuid,
        displayUrl: document.display_url ?? "",
        fileName: document.filename ?? "",
        mimeType: document.mime_type,
        fileSize: document.file_size,
        order: images.length + index,
      })),
  ];
  if (localImages.length) {
    // 与服务端写入一致的 iOS 形态：_0 直接是图片数组；id/type 为 iOS 必填字段
    blocks.push({
      id: `${sent.client_message_id}-gallery`,
      kind: "imageGallery",
      status: "ready",
      revision: 1,
      order_key: 1100,
      node_role: "timeline",
      payload: {
        image_gallery: {
          _0: localImages.map((image) => ({
            id: image.fileUuid ?? crypto.randomUUID(),
            type: "image",
            file_id: image.fileId,
            url: image.displayUrl,
            filename: image.fileName,
            mime_type: image.mimeType,
            order: image.order,
          })),
        },
      },
    });
  }
  const localDocuments = documents.filter((document) => document.type === "document");
  if (localDocuments.length) {
    blocks.push({
      id: `${sent.client_message_id}-files`,
      kind: "fileGallery",
      status: "ready",
      revision: 1,
      order_key: 1200,
      node_role: "timeline",
      payload: {
        file_gallery: {
          _0: localDocuments.map((document) => ({
            id: document.file_uuid ?? crypto.randomUUID(),
            type: "document",
            file_id: document.file_id,
            url: document.display_url,
            filename: document.filename,
            mime_type: document.mime_type,
            file_size: document.file_size,
            order: document.order,
          })),
        },
      },
    });
  }
  return {
    thread_id: sent.thread_id,
    role: "assistant",
    client_message_id: sent.client_message_id,
    server_message_id: sent.server_message_id,
    delivery_state: "sent",
    created_at: sent.created_at,
    actor_type: "doctor",
    sender: sent.sender,
    attachments: [
      ...images.map((image) => ({
        id: image.fileUuid ?? crypto.randomUUID(),
        file_id: image.fileId,
        type: "image" as const,
        order: image.order,
        mime_type: image.mimeType,
        file_size: image.fileSize,
        display_url: image.displayUrl,
      })),
      ...documents.map((document) => ({
        id: document.file_uuid ?? crypto.randomUUID(),
        file_id: String(document.file_id),
        type: document.type,
        order: document.order,
        mime_type: document.mime_type,
        file_size: document.file_size,
        display_url: document.display_url,
      })),
    ],
    blocks,
  };
}
