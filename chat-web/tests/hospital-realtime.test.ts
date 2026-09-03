import { describe, expect, it, vi } from "vitest";
import {
  CoalescedRefreshScheduler,
  DirtySyncScheduler,
  doctorConversationWebSocketUrl,
  doctorMessageStableKey,
  isHospitalConversationUpdatedEvent,
  mergeAuthoritativeSnapshot,
  realtimeRetryDelay,
  sliceAppendedMessages,
} from "@/lib/hospital/realtime";
import type { DoctorMessageDTO } from "@/types/hospital";

function message(partial: Partial<DoctorMessageDTO> & { client_message_id: string }): DoctorMessageDTO {
  return {
    thread_id: "thread-1",
    role: "user",
    delivery_state: "sent",
    created_at: "2026-09-02T10:00:00Z",
    blocks: [],
    ...partial,
  };
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe("isHospitalConversationUpdatedEvent", () => {
  it("accepts a well-formed hint without message bodies", () => {
    expect(isHospitalConversationUpdatedEvent({
      type: "hospital.conversation.updated",
      payload_version: 1,
      event_id: "evt-1",
      thread_id: "thread-1",
      message_ids: ["m-1"],
      cursor: "2026-09-02T10:00:00Z",
    })).toBe(true);
  });

  it("accepts the minimal contract (type + thread_id only)", () => {
    expect(isHospitalConversationUpdatedEvent({ type: "hospital.conversation.updated", thread_id: "t" })).toBe(true);
  });

  it("rejects other event types and malformed payloads", () => {
    expect(isHospitalConversationUpdatedEvent(null)).toBe(false);
    expect(isHospitalConversationUpdatedEvent("hospital.conversation.updated")).toBe(false);
    expect(isHospitalConversationUpdatedEvent({ type: "chat.sync.hint", thread_id: "t" })).toBe(false);
    expect(isHospitalConversationUpdatedEvent({ type: "hospital.conversation.updated" })).toBe(false);
    expect(isHospitalConversationUpdatedEvent({ type: "hospital.conversation.updated", thread_id: "" })).toBe(false);
  });
});

describe("mergeAuthoritativeSnapshot", () => {
  it("returns the snapshot untouched when there is no optimistic pending", () => {
    const snapshot = [message({ client_message_id: "c1", server_message_id: "s1" })];
    expect(mergeAuthoritativeSnapshot(snapshot, [])).toBe(snapshot);
  });

  it("drops optimistic messages confirmed by server_message_id or client_message_id", () => {
    const snapshot = [message({ client_message_id: "c1", server_message_id: "s1" })];
    const pending = [
      message({ client_message_id: "c1" }),
      message({ client_message_id: "c9", server_message_id: "s1" }),
    ];
    expect(mergeAuthoritativeSnapshot(snapshot, pending)).toEqual(snapshot);
  });

  it("keeps unconfirmed optimistic messages after the snapshot", () => {
    const snapshot = [message({ client_message_id: "c1", server_message_id: "s1" })];
    const pending = [message({ client_message_id: "c2" })];
    const merged = mergeAuthoritativeSnapshot(snapshot, pending);
    expect(merged.map((item) => item.client_message_id)).toEqual(["c1", "c2"]);
  });
});

describe("DirtySyncScheduler", () => {
  it("runs the first request immediately and coalesces in-flight events into one trailing run", async () => {
    const runner = vi.fn<(threadId: string) => Promise<void>>();
    let release: () => void = () => undefined;
    runner.mockImplementation(() => new Promise<void>((resolve) => { release = resolve; }));
    const scheduler = new DirtySyncScheduler(runner);

    scheduler.request("t1");
    expect(runner).toHaveBeenCalledTimes(1);
    scheduler.request("t1");
    scheduler.request("t1");
    release();
    await flush();
    expect(runner).toHaveBeenCalledTimes(2);
    release();
    await flush();
    expect(runner).toHaveBeenCalledTimes(2);
  });

  it("tracks different threads independently", async () => {
    const runner = vi.fn<(threadId: string) => Promise<void>>().mockResolvedValue(undefined);
    const scheduler = new DirtySyncScheduler(runner);
    scheduler.request("t1");
    scheduler.request("t2");
    await flush();
    expect(runner.mock.calls.map(([id]) => id)).toEqual(["t1", "t2"]);
  });

  it("keeps scheduling after a runner failure", async () => {
    const runner = vi.fn<(threadId: string) => Promise<void>>()
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue(undefined);
    const scheduler = new DirtySyncScheduler(runner);
    scheduler.request("t1");
    await flush();
    scheduler.request("t1");
    await flush();
    expect(runner).toHaveBeenCalledTimes(2);
  });
});

describe("CoalescedRefreshScheduler", () => {
  it("merges requests inside the window into a single run", async () => {
    vi.useFakeTimers();
    try {
      const runner = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
      const scheduler = new CoalescedRefreshScheduler(runner, 100);
      scheduler.request();
      scheduler.request();
      scheduler.request();
      await vi.advanceTimersByTimeAsync(100);
      expect(runner).toHaveBeenCalledTimes(1);
      scheduler.dispose();
    } finally {
      vi.useRealTimers();
    }
  });

  it("runs a trailing pass when requests arrive during an in-flight run", async () => {
    vi.useFakeTimers();
    try {
      let release: () => void = () => undefined;
      const runner = vi.fn<() => Promise<void>>().mockImplementation(
        () => new Promise<void>((resolve) => { release = resolve; }),
      );
      const scheduler = new CoalescedRefreshScheduler(runner, 100);
      scheduler.request();
      await vi.advanceTimersByTimeAsync(100);
      expect(runner).toHaveBeenCalledTimes(1);
      scheduler.request();
      await vi.advanceTimersByTimeAsync(100);
      release();
      await vi.advanceTimersByTimeAsync(100);
      expect(runner).toHaveBeenCalledTimes(2);
      scheduler.dispose();
    } finally {
      vi.useRealTimers();
    }
  });

  it("cancels a pending window on dispose", async () => {
    vi.useFakeTimers();
    try {
      const runner = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
      const scheduler = new CoalescedRefreshScheduler(runner, 100);
      scheduler.request();
      scheduler.dispose();
      await vi.advanceTimersByTimeAsync(500);
      expect(runner).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("realtimeRetryDelay", () => {
  it("grows exponentially and caps at 30s", () => {
    expect(realtimeRetryDelay(0)).toBe(1000);
    expect(realtimeRetryDelay(1)).toBe(2000);
    expect(realtimeRetryDelay(5)).toBe(30_000);
    expect(realtimeRetryDelay(12)).toBe(30_000);
  });
});

describe("doctorMessageStableKey / sliceAppendedMessages", () => {
  it("prefers client_message_id and falls back to server_message_id", () => {
    expect(doctorMessageStableKey(message({ client_message_id: "c1", server_message_id: "s1" }))).toBe("c1");
    expect(doctorMessageStableKey({ ...message({ client_message_id: "" }), server_message_id: "s9" })).toBe("s9");
    expect(doctorMessageStableKey(undefined)).toBeNull();
  });

  it("returns messages appended after the anchor key", () => {
    const items = [
      message({ client_message_id: "c1" }),
      message({ client_message_id: "c2" }),
      message({ client_message_id: "c3" }),
    ];
    expect(sliceAppendedMessages("c1", items).map((item) => item.client_message_id)).toEqual(["c2", "c3"]);
    expect(sliceAppendedMessages("c3", items)).toEqual([]);
  });

  it("returns empty when the anchor is missing (full snapshot replace) or absent", () => {
    const items = [message({ client_message_id: "c1" })];
    expect(sliceAppendedMessages("gone", items)).toEqual([]);
    expect(sliceAppendedMessages(null, items)).toEqual([]);
    expect(sliceAppendedMessages("c1", [])).toEqual([]);
  });
});

describe("doctorConversationWebSocketUrl", () => {
  it("builds a same-origin ws url carrying the one-time ticket", () => {
    const url = doctorConversationWebSocketUrl("/ws/hospital/doctor/conversations/", "ticket-abc");
    expect(url).toContain("/ws/hospital/doctor/conversations/");
    expect(url).toContain("ticket=ticket-abc");
    expect(url.startsWith("ws://") || url.startsWith("wss://")).toBe(true);
  });
});
