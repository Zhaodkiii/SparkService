import { afterEach, describe, expect, it, vi } from "vitest";
import {
  IMAGE_MAX_EDGE,
  IMAGE_MAX_OUTPUT_BYTES,
  ImageNormalizeError,
  assertImageFileType,
  assertOutputSize,
  computeContainSize,
  normalizeImageForUpload,
  normalizedFileName,
} from "@/lib/chat/image-normalize";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("image normalize 纯计算", () => {
  it("拒绝非 image/* 输入", () => {
    expect(() => assertImageFileType("application/pdf")).toThrowError(ImageNormalizeError);
    try {
      assertImageFileType("text/plain");
    } catch (cause) {
      expect(cause).toBeInstanceOf(ImageNormalizeError);
      expect((cause as ImageNormalizeError).code).toBe("chat_image_format_invalid");
    }
    expect(() => assertImageFileType("image/png")).not.toThrow();
  });

  it("computeContainSize 最长边缩放到 2048 且不放大原图", () => {
    expect(computeContainSize(4000, 2000)).toEqual({ width: IMAGE_MAX_EDGE, height: 1024 });
    expect(computeContainSize(1000, 3000)).toEqual({ width: 683, height: IMAGE_MAX_EDGE });
    expect(computeContainSize(800, 600)).toEqual({ width: 800, height: 600 });
  });

  it("normalizedFileName 按编码格式改写后缀", () => {
    expect(normalizedFileName("IMG_001.PNG", "image/webp")).toBe("IMG_001.webp");
    expect(normalizedFileName("photo.jpeg", "image/jpeg")).toBe("photo.jpg");
    expect(normalizedFileName("", "image/webp")).toBe("image.webp");
  });

  it("assertOutputSize 超过 10MB 抛错", () => {
    expect(() => assertOutputSize(IMAGE_MAX_OUTPUT_BYTES)).not.toThrow();
    try {
      assertOutputSize(IMAGE_MAX_OUTPUT_BYTES + 1);
    } catch (cause) {
      expect((cause as ImageNormalizeError).code).toBe("chat_image_normalize_failed");
      return;
    }
    throw new Error("应当抛错");
  });
});

describe("normalizeImageForUpload", () => {
  function mockCanvas(toBlobImpl: (callback: BlobCallback, type?: string) => void) {
    vi.stubGlobal("createImageBitmap", vi.fn(async () => ({ width: 4000, height: 2000, close: vi.fn() })));
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (callback: BlobCallback, type?: string) {
      toBlobImpl(callback, type);
    });
  }

  it("压缩为 webp 并改写文件名与尺寸", async () => {
    mockCanvas((callback, type) => callback(new Blob(["x".repeat(100)], { type: type ?? "image/webp" })));
    const file = new File(["raw"], "IMG_001.png", { type: "image/png" });
    const result = await normalizeImageForUpload(file);
    expect(result.mimeType).toBe("image/webp");
    expect(result.fileName).toBe("IMG_001.webp");
    expect(result.width).toBe(IMAGE_MAX_EDGE);
    expect(result.height).toBe(1024);
    expect(result.fileSize).toBe(result.blob.size);
  });

  it("浏览器不支持 webp 时回退 jpeg", async () => {
    mockCanvas((callback, type) => {
      // 模拟 Safari：请求 webp 时实际返回 png。
      const actual = type === "image/webp" ? "image/png" : (type ?? "image/jpeg");
      callback(new Blob(["x"], { type: actual }));
    });
    const file = new File(["raw"], "photo.png", { type: "image/png" });
    const result = await normalizeImageForUpload(file);
    expect(result.mimeType).toBe("image/jpeg");
    expect(result.fileName).toBe("photo.jpg");
  });

  it("解码失败抛 chat_image_format_invalid", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn(async () => { throw new Error("decode failed"); }));
    const file = new File(["raw"], "broken.png", { type: "image/png" });
    await expect(normalizeImageForUpload(file)).rejects.toMatchObject({ code: "chat_image_format_invalid" });
  });

  it("非图片输入直接拒绝", async () => {
    const file = new File(["raw"], "notes.txt", { type: "text/plain" });
    await expect(normalizeImageForUpload(file)).rejects.toMatchObject({ code: "chat_image_format_invalid" });
  });
});
