import { describe, expect, it } from "vitest";
import { coherentEvents, gapEvents, unknownEvent, TEXT_BLOCK_ID, RUN_ID } from "@/fixtures/chat/scenarios";
import { createInitialChatRuntimeState, reduceChatEvent, reduceChatEvents } from "@/lib/event-reducer";

describe("Spark chat event reducer", () => {
  it("projects a coherent run and block", () => {
    const state = reduceChatEvents(createInitialChatRuntimeState(), coherentEvents);
    expect(state.runsById[RUN_ID].status).toBe("completed");
    expect(state.runsById[RUN_ID].last_sequence).toBe(8);
    expect(state.blocksById[TEXT_BLOCK_ID].payload.text).toContain("P0 静态契约回答");
    expect(state.blocksById[TEXT_BLOCK_ID].status).toBe("ready");
  });

  it("deduplicates event ids and rejects stale revisions", () => {
    let state = reduceChatEvents(createInitialChatRuntimeState(), coherentEvents);
    const duplicate = reduceChatEvent(state, coherentEvents[4]);
    expect(duplicate).toEqual(state);
    const stale = { ...coherentEvents[4], event_id: "00000000-0000-0000-0000-000000009999", sequence: 9, payload: { ...coherentEvents[4].payload, revision: 1, delta: "旧内容" } };
    state = reduceChatEvent(state, stale);
    expect(state.blocksById[TEXT_BLOCK_ID].payload.text).not.toContain("旧内容");
  });

  it("buffers a sequence gap and drains it when the missing event arrives", () => {
    let state = createInitialChatRuntimeState();
    state = reduceChatEvent(state, gapEvents[0]);
    state = reduceChatEvent(state, gapEvents[1]);
    expect(state.replayRequiredByRun[RUN_ID]).toBe(true);
    state = reduceChatEvent(state, gapEvents[2]);
    expect(state.replayRequiredByRun[RUN_ID]).toBe(false);
    expect(state.lastAppliedSequenceByRun[RUN_ID]).toBe(3);
  });

  it("retains unknown events without crashing", () => {
    const state = reduceChatEvent(createInitialChatRuntimeState(), unknownEvent);
    expect(state.unknownActivitiesByRun[RUN_ID]).toHaveLength(1);
  });
});
