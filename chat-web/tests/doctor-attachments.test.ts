import { describe, expect, it } from "vitest";
import {
  allAttachmentsReady,
  formatFileSize,
  hasPendingAttachment,
  newAttachmentDraft,
  readyAttachmentPayloads,
  updateAttachment,
  validateAttachmentFile,
} from "@/lib/hospital/attachments";
import { endReasonLabel } from "@/lib/hospital/labels";

function file(name: string, type: string, size = 1024): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe("doctor conversation attachments", () => {
  it("accepts pdf/jpg/png within limits", () => {
    expect(validateAttachmentFile(file("报告.pdf", "application/pdf"))).toBeNull();
    expect(validateAttachmentFile(file("片子.jpg", "image/jpeg"))).toBeNull();
    expect(validateAttachmentFile(file("化验单.png", "image/png"))).toBeNull();
  });

  it("rejects unsupported types and oversize files", () => {
    expect(validateAttachmentFile(file("笔记.txt", "text/plain"))).toMatch(/PDF/);
    expect(validateAttachmentFile(file("伪装.pdf", "image/png"))).toMatch(/PDF/);
    expect(validateAttachmentFile(file("大文件.pdf", "application/pdf", 21 * 1024 * 1024))).toMatch(/20 MB/);
  });

  it("builds send payloads only from ready drafts", () => {
    const draft = newAttachmentDraft(file("报告.pdf", "application/pdf"));
    expect(allAttachmentsReady([draft])).toBe(false);
    expect(hasPendingAttachment([draft])).toBe(true);
    const ready = updateAttachment([draft], draft.id, { status: "ready", fileId: 2568, displayUrl: "https://oss.example/a.pdf" });
    expect(allAttachmentsReady(ready)).toBe(true);
    const payloads = readyAttachmentPayloads(ready);
    expect(payloads).toHaveLength(1);
    expect(payloads[0]).toMatchObject({ file_id: 2568, type: "document", mime_type: "application/pdf", order: 0 });
  });

  it("classifies image attachments as image payloads", () => {
    const draft = newAttachmentDraft(file("片子.png", "image/png"));
    const ready = updateAttachment([draft], draft.id, { status: "ready", fileId: 99 });
    expect(readyAttachmentPayloads(ready)[0].type).toBe("image");
  });

  it("formats file sizes", () => {
    expect(formatFileSize(512)).toBe("512 B");
    expect(formatFileSize(2048)).toBe("2.0 KB");
    expect(formatFileSize(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});

describe("endReasonLabel", () => {
  it("prefers the stored display text", () => {
    expect(endReasonLabel({ end_reason: "已完成咨询", end_reason_code: "resolved", end_reason_note: "" })).toBe("已完成咨询");
  });

  it("falls back to the enum label", () => {
    expect(endReasonLabel({ end_reason: "", end_reason_code: "offline_referral", end_reason_note: "" })).toBe("建议线下就诊");
  });

  it("appends the note for other reasons", () => {
    expect(endReasonLabel({ end_reason: "", end_reason_code: "other", end_reason_note: "患者改约" })).toBe("其他：患者改约");
  });
});
