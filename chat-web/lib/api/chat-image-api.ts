import type { SparkHttpClient } from "@/lib/api/http-client";
import type {
  ChatImageCompleteDTO,
  ChatImageCompleteRequestDTO,
  ChatImageUploadSessionDTO,
  ChatImageUploadSessionRequestDTO,
} from "@/types/chat-image";

function pathSegment(value: string): string {
  return encodeURIComponent(value);
}

/**
 * 聊天图片上传 API（CHAT-WEB-029）。
 * 构造方式与 SparkRunApi 一致：复用 AuthContext 注入的 SparkHttpClient
 * （同源代理 + Bearer token）。两个接口均以 client_upload_id 作为幂等键。
 */
export class SparkChatImageApi {
  constructor(private readonly http: SparkHttpClient) {}

  createUploadSession(body: ChatImageUploadSessionRequestDTO): Promise<ChatImageUploadSessionDTO> {
    return this.http.requestOrThrow("POST", "/api/v1/oss/chat-images/upload-sessions/", {
      body,
      headers: { "Idempotency-Key": body.client_upload_id },
    });
  }

  completeUpload(sessionId: string, body: ChatImageCompleteRequestDTO): Promise<ChatImageCompleteDTO> {
    return this.http.requestOrThrow("POST", `/api/v1/oss/chat-images/upload-sessions/${pathSegment(sessionId)}/complete/`, {
      body,
      headers: { "Idempotency-Key": body.client_upload_id },
    });
  }
}
