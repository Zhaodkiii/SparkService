import { describe, expect, it } from "vitest";
import { addTurnContextItem, emptyTurnContextDraft, removeTurnContextItem, toCreateTurnContextInput } from "@/lib/context/turn-context-draft";

describe("turn context draft", () => {
  it("deduplicates items, enforces the server limit and maps only ready IDs", () => {
    let draft = emptyTurnContextDraft("thread-1");
    draft = addTurnContextItem(draft, { key: "attachment:file:10", kind: "attachment", fileId: "10", title: "file", status: "ready" });
    draft = addTurnContextItem(draft, { key: "attachment:file:10", kind: "attachment", fileId: "10", title: "duplicate", status: "ready" });
    draft = addTurnContextItem(draft, { key: "attachment:file:11", kind: "attachment", fileId: "11", title: "pending", status: "registering" });
    expect(draft.items).toHaveLength(2);
    expect(toCreateTurnContextInput(draft, 3)).toEqual({ preferencesRevision: 3, contextParentMessageId: null, references: [], attachments: [{ file_id: "10" }] });
    expect(removeTurnContextItem(draft, "attachment:file:10").items).toHaveLength(1);
  });
});
