import type { SparkHttpClient } from "@/lib/api/http-client";
import type {
  ChatMessageWireDTO,
  ChatThreadWireDTO,
  MessagePullData,
  ThreadDeleteData,
  ThreadDeleteRequest,
  ThreadPullData,
  ThreadPushData,
  ThreadPushRequest,
} from "@/types/sync";
import { normalizeMessageBlocks } from "@/lib/chat/message-normalizer";
export { normalizeSyncBlock } from "@/lib/chat/block-normalizer";

function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== undefined) params.set(key, String(value));
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export class SparkChatSyncApi {
  constructor(private readonly http: SparkHttpClient) {}

  pullThreads(cursor?: string, limit = 100): Promise<ThreadPullData> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/sync/thread-pull/${query({ cursor, limit })}`);
  }

  pushThreads(threads: ChatThreadWireDTO[]): Promise<ThreadPushData> {
    const payload: ThreadPushRequest = { threads };
    return this.http.requestOrThrow("POST", "/api/v1/ai/chat/sync/thread-push/", { body: payload });
  }

  deleteThreads(threadIds: string[]): Promise<ThreadDeleteData> {
    const payload: ThreadDeleteRequest = { thread_ids: threadIds };
    return this.http.requestOrThrow("POST", "/api/v1/ai/chat/sync/thread-delete/", { body: payload });
  }

  async pullMessages(threadId: string, cursor?: string, limit = 100): Promise<MessagePullData> {
    const data = await this.http.requestOrThrow<MessagePullData>("GET", `/api/v1/ai/chat/sync/pull/${query({ thread_id: threadId, cursor, limit })}`);
    return { ...data, messages: data.messages.map((message) => ({ ...message, blocks: normalizeMessageBlocks(message.blocks) })) };
  }

  threadHead(threadId: string): Promise<{ thread_id: string; last_server_updated_at: string | null }> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/sync/thread-head/${query({ thread_id: threadId })}`);
  }

  pushMessage(payload: ChatMessageWireDTO): Promise<unknown> {
    return this.http.requestOrThrow("POST", "/api/v1/ai/chat/sync/push/", { body: { messages: [payload] } });
  }
}
