import { describe, expect, it } from "vitest";
import { toLocalDoctorMessage } from "@/lib/api/hospital-api";
import type { ReadyImagePayload } from "@/lib/chat/image-drafts";
import type { DoctorSendMessageDTO } from "@/types/hospital";

const sent: DoctorSendMessageDTO = {
  message_id: 1,
  server_message_id: "srv-1",
  client_message_id: "cli-1",
  thread_id: "thread-1",
  role: "assistant",
  created_at: "2026-09-01T10:32:00.000Z",
  sender: { display_name: "张医生" },
  version: 3,
};

const image: ReadyImagePayload = {
  fileId: "2568",
  fileUuid: "7e4b4c1f-8f5c-4b0c-9f3e-2f6a9b0c1d2e",
  displayUrl: "https://oss.example/a.webp",
  fileName: "a.webp",
  mimeType: "image/webp",
  fileSize: 1024,
  order: 0,
};

describe("toLocalDoctorMessage", () => {
  it("纯文本：只有 text block，无附件", () => {
    const local = toLocalDoctorMessage(sent, "请卧床休息");
    expect(local.blocks).toHaveLength(1);
    expect(local.blocks[0].kind).toBe("text");
    expect(local.attachments).toEqual([]);
  });

  it("图文：text + imageGallery（iOS 数组形态）+ attachments", () => {
    const local = toLocalDoctorMessage(sent, "看这张", [image]);
    expect(local.blocks.map((block) => block.kind)).toEqual(["text", "imageGallery"]);
    expect(local.blocks[1].payload).toEqual({
      image_gallery: {
        _0: [{ id: "7e4b4c1f-8f5c-4b0c-9f3e-2f6a9b0c1d2e", type: "image", file_id: "2568", url: "https://oss.example/a.webp", filename: "a.webp", mime_type: "image/webp", order: 0 }],
      },
    });
    expect(local.attachments).toEqual([
      { id: "7e4b4c1f-8f5c-4b0c-9f3e-2f6a9b0c1d2e", file_id: "2568", type: "image", order: 0, mime_type: "image/webp", file_size: 1024, display_url: "https://oss.example/a.webp" },
    ]);
  });

  it("图片-only：无 text block", () => {
    const local = toLocalDoctorMessage(sent, "", [image]);
    expect(local.blocks.map((block) => block.kind)).toEqual(["imageGallery"]);
  });
});
