/**
 * 聊天图片上传契约（CHAT-WEB-029）：服务端签发上传会话，浏览器直传 OSS，
 * 完成后登记 ManagedFile。所有字段与服务端 `/api/v1/oss/chat-images/` 对齐。
 */

/** 创建上传会话请求体。`client_upload_id` 由客户端生成，重复时返回同一会话。 */
export interface ChatImageUploadSessionRequestDTO {
  purpose: "chat_image";
  thread_id?: string | null;
  mime_type: string;
  file_size: number;
  client_upload_id: string;
}

/** 创建上传会话响应 data。 */
export interface ChatImageUploadSessionDTO {
  upload_session_id: string;
  object_key: string;
  upload_url: string;
  upload_url_expires_in: number;
  display_url: string;
  method: "PUT";
  required_headers: Record<string, string>;
  max_file_size: number;
  expires_at: string;
}

/** 完成上传（登记 ManagedFile）请求体。file_md5 可选，本期不发送。 */
export interface ChatImageCompleteRequestDTO {
  client_upload_id: string;
  object_key: string;
  mime_type: string;
  file_size: number;
  file_md5?: string;
}

/** 完成上传响应 data。重复提交返回同一 `file_id`。 */
export interface ChatImageCompleteDTO {
  file_id: string;
  file_uuid: string;
  status: "ready";
  display_url: string;
  version: string;
}
