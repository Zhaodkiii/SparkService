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
import type { ChatBlockDTO } from "@/types/chat";

const BLOCK_META_KEYS = new Set(["id", "kind", "status", "revision", "order_key", "tool_call_id", "parent_tool_call_id", "parent_block_id", "node_role", "anchor", "created_at", "updated_at"]);

export function normalizeSyncBlock(raw: Record<string, unknown>): ChatBlockDTO {
  const explicitPayload = raw.payload && typeof raw.payload === "object" ? raw.payload as Record<string, unknown> : null;
  const payload = explicitPayload ?? Object.fromEntries(Object.entries(raw).filter(([key]) => !BLOCK_META_KEYS.has(key)));
  return {
    id: String(raw.id ?? ""),
    kind: String(raw.kind ?? "text"),
    status: (["pending", "streaming", "ready", "failed"].includes(String(raw.status)) ? raw.status : "ready") as ChatBlockDTO["status"],
    revision: Number(raw.revision ?? 0),
    order_key: typeof raw.order_key === "number" ? raw.order_key : null,
    tool_call_id: typeof raw.tool_call_id === "string" ? raw.tool_call_id : null,
    parent_tool_call_id: typeof raw.parent_tool_call_id === "string" ? raw.parent_tool_call_id : null,
    parent_block_id: typeof raw.parent_block_id === "string" ? raw.parent_block_id : null,
    node_role: String(raw.node_role ?? "timeline"),
    anchor: raw.anchor && typeof raw.anchor === "object" ? raw.anchor as Record<string, unknown> : null,
    payload,
    created_at: typeof raw.created_at === "string" ? raw.created_at : undefined,
    updated_at: typeof raw.updated_at === "string" ? raw.updated_at : undefined,
  };
}

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
    return { ...data, messages: data.messages.map((message) => ({ ...message, blocks: message.blocks.map((block) => normalizeSyncBlock(block as unknown as Record<string, unknown>)) })) };
  }

  threadHead(threadId: string): Promise<{ thread_id: string; last_server_updated_at: string | null }> {
    return this.http.requestOrThrow("GET", `/api/v1/ai/chat/sync/thread-head/${query({ thread_id: threadId })}`);
  }

  pushMessage(payload: ChatMessageWireDTO): Promise<unknown> {
    return this.http.requestOrThrow("POST", "/api/v1/ai/chat/sync/push/", { body: { messages: [payload] } });
  }
}
