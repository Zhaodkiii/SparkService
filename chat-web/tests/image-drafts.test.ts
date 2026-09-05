import { describe, expect, it } from "vitest";
import {
  MAX_IMAGE_DRAFTS,
  addDrafts,
  allReady,
  hasPendingDrafts,
  markSending,
  markSent,
  removeDraft,
  resetForRetry,
  toReadyImagePayloads,
  updateDraft,
} from "@/lib/chat/image-drafts";
import type { ImageDraft } from "@/lib/chat/image-drafts";

function draft(id: string, status: ImageDraft["status"] = "selected"): ImageDraft {
  return { id, fileName: `${id}.png`, previewUrl: `blob:${id}`, status, progress: 0 };
}

describe("image drafts 状态机", () => {
  it("addDrafts 最多保留 3 张，超出部分被拒绝", () => {
    const existing = [draft("a", "ready")];
    const incoming = [draft("b"), draft("c"), draft("d")];
    const result = addDrafts(existing, incoming);
    expect(MAX_IMAGE_DRAFTS).toBe(3);
    expect(result.drafts.map((item) => item.id)).toEqual(["a", "b", "c"]);
    expect(result.rejected.map((item) => item.id)).toEqual(["d"]);
    // 已有 3 张时全部拒绝
    const full = addDrafts(result.drafts, [draft("e")]);
    expect(full.drafts).toHaveLength(3);
    expect(full.rejected).toHaveLength(1);
  });

  it("updateDraft/removeDraft 按 id 精确更新与移除", () => {
    let drafts = [draft("a"), draft("b")];
    drafts = updateDraft(drafts, "a", { status: "uploading", progress: 40 });
    expect(drafts[0]).toMatchObject({ status: "uploading", progress: 40 });
    expect(drafts[1].status).toBe("selected");
    drafts = removeDraft(drafts, "a");
    expect(drafts.map((item) => item.id)).toEqual(["b"]);
  });

  it("allReady/hasPendingDrafts 只在全部 ready 时允许发送", () => {
    expect(allReady([])).toBe(false);
    expect(allReady([draft("a", "ready"), draft("b", "uploading")])).toBe(false);
    expect(allReady([draft("a", "ready"), draft("b", "ready")])).toBe(true);
    expect(hasPendingDrafts([draft("a", "failed")])).toBe(true);
    expect(hasPendingDrafts([draft("a", "ready"), draft("b", "sending")])).toBe(false);
  });

  it("markSending/markSent 驱动 ready → sending → sent", () => {
    let drafts = [draft("a", "ready"), draft("b", "failed")];
    drafts = markSending(drafts);
    expect(drafts[0].status).toBe("sending");
    expect(drafts[1].status).toBe("failed");
    drafts = markSent(drafts);
    expect(drafts[0].status).toBe("sent");
  });

  it("CreateRun 失败后 resetForRetry：sending 回到 ready 且保留 fileId", () => {
    const ready = { ...draft("a", "ready"), fileId: "file-1", displayUrl: "https://oss.example/a.webp" };
    let drafts = markSending([ready, draft("b", "ready")]);
    expect(drafts.every((item) => item.status === "sending")).toBe(true);
    drafts = resetForRetry(drafts);
    expect(drafts[0]).toMatchObject({ status: "ready", fileId: "file-1", displayUrl: "https://oss.example/a.webp" });
    expect(drafts[1].status).toBe("ready");
  });

  it("toReadyImagePayloads 按选择顺序输出 fileId 与 order", () => {
    const drafts = [
      { ...draft("a", "ready"), fileId: "file-a", fileName: "a.webp", mimeType: "image/webp", fileSize: 100 },
      draft("b", "uploading"),
      { ...draft("c", "ready"), fileId: "file-c", fileName: "c.webp" },
    ];
    expect(toReadyImagePayloads(drafts)).toEqual([
      { fileId: "file-a", fileName: "a.webp", mimeType: "image/webp", fileSize: 100, displayUrl: undefined, order: 0 },
      { fileId: "file-c", fileName: "c.webp", mimeType: undefined, fileSize: undefined, displayUrl: undefined, order: 1 },
    ]);
  });
});
