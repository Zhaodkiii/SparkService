import type { DoctorMessageDTO, HospitalConversationUpdatedEvent } from "@/types/hospital";

/** BACKOFFICE-CONVERSATION-000002 §8.2.3：医生工作台实时事件守卫。 */
export function isHospitalConversationUpdatedEvent(value: unknown): value is HospitalConversationUpdatedEvent {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return record.type === "hospital.conversation.updated" && typeof record.thread_id === "string" && record.thread_id.length > 0;
}

/** BACKOFFICE-CONVERSATION-000002 Q11：以服务端完整快照为权威，
 *  仅保留尚未被快照确认的医生本地乐观消息（server_message_id 优先、
 *  client_message_id 兜底的稳定键，不按正文去重）。 */
export function mergeAuthoritativeSnapshot(
  snapshot: DoctorMessageDTO[],
  optimisticPending: DoctorMessageDTO[],
): DoctorMessageDTO[] {
  if (!optimisticPending.length) return snapshot;
  const confirmed = new Set<string>();
  for (const item of snapshot) {
    if (item.server_message_id) confirmed.add(`s:${item.server_message_id}`);
    if (item.client_message_id) confirmed.add(`c:${item.client_message_id}`);
  }
  const pending = optimisticPending.filter((item) => {
    if (item.server_message_id && confirmed.has(`s:${item.server_message_id}`)) return false;
    if (item.client_message_id && confirmed.has(`c:${item.client_message_id}`)) return false;
    return true;
  });
  if (!pending.length) return snapshot;
  return [...snapshot, ...pending];
}

/** BACKOFFICE-CONVERSATION-000002 Q6：同一 thread 首条事件立即执行，
 *  在途期间的事件只标记 dirty，本轮结束后补跑一轮，直至没有新事件。 */
export class DirtySyncScheduler {
  private readonly states = new Map<string, { inFlight: boolean; dirty: boolean }>();

  constructor(private readonly runner: (threadId: string) => Promise<void>) {}

  request(threadId: string): void {
    const state = this.states.get(threadId);
    if (state?.inFlight) {
      state.dirty = true;
      return;
    }
    this.states.set(threadId, { inFlight: true, dirty: false });
    void this.run(threadId);
  }

  private async run(threadId: string): Promise<void> {
    try {
      await this.runner(threadId);
    } catch {
      // runner 内部已处理错误分类；调度器只负责 dirty 语义。
    } finally {
      const state = this.states.get(threadId);
      this.states.delete(threadId);
      if (state?.dirty) this.request(threadId);
    }
  }
}

/** BACKOFFICE-CONVERSATION-000002 §8.3.3：列表/计数刷新短窗口合并，
 *  在途期间的请求合并为一轮尾随补跑，避免连续事件造成请求风暴。 */
export class CoalescedRefreshScheduler {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private inFlight = false;
  private pending = false;

  constructor(
    private readonly runner: () => Promise<void>,
    private readonly delayMs = 250,
  ) {}

  request(): void {
    if (this.timer !== null) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.flush();
    }, this.delayMs);
  }

  private async flush(): Promise<void> {
    if (this.inFlight) {
      this.pending = true;
      return;
    }
    this.inFlight = true;
    try {
      await this.runner();
    } catch {
      // runner 内部已处理错误分类；调度器只负责合并语义。
    } finally {
      this.inFlight = false;
      if (this.pending) {
        this.pending = false;
        this.request();
      }
    }
  }

  dispose(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.pending = false;
  }
}

/** BACKOFFICE-CONVERSATION-000002 §8.3.1：指数退避 1s→2s→…→30s 上限（抖动由调用方叠加）。 */
export function realtimeRetryDelay(attempt: number): number {
  return Math.min(30_000, 1000 * 2 ** Math.min(Math.max(attempt, 0), 5));
}

/** 与 RunControlContext 相同的 ws(s) URL 推导：默认同源，可用 NEXT_PUBLIC_SPARK_WS_BASE_URL 覆盖。 */
export function doctorConversationWebSocketUrl(path: string, ticket: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const configuredBase = process.env.NEXT_PUBLIC_SPARK_WS_BASE_URL;
  const url = new URL(path, configuredBase || `${protocol}//${window.location.host}`);
  url.searchParams.set("ticket", ticket);
  return url.toString();
}

/** BACKOFFICE-CONVERSATION-000002 Q4：消息稳定键（client_message_id 优先，server_message_id 兜底）。 */
export function doctorMessageStableKey(message: DoctorMessageDTO | undefined): string | null {
  if (!message) return null;
  return message.client_message_id || message.server_message_id || null;
}

/** 以“上一轮最后一条消息”为锚点计算本轮追加的消息（从尾部查找，容忍重复键）。
 *  锚点为空或锚点已不在列表中（完整快照替换/重排）时返回空数组，调用方按快照刷新处理。 */
export function sliceAppendedMessages(previousLastKey: string | null, messages: DoctorMessageDTO[]): DoctorMessageDTO[] {
  if (!previousLastKey || !messages.length) return [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (doctorMessageStableKey(messages[index]) === previousLastKey) {
      return messages.slice(index + 1);
    }
  }
  return [];
}
