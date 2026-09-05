/**
 * 图片标准化压缩（CHAT-WEB-029 §6.2）。
 *
 * 上传前统一处理：EXIF 方向修正、最长边缩放到 ≤2048px、编码为 WebP
 * （浏览器不支持时回退 JPEG）、质量 0.85、输出 ≤10MB。
 * 处理失败不进入上传，草稿由调用方标记 failed。
 */

/** 标准化图片最长边。 */
export const IMAGE_MAX_EDGE = 2048;
/** 标准化输出大小上限（10MB）。 */
export const IMAGE_MAX_OUTPUT_BYTES = 10 * 1024 * 1024;
/** 编码质量。 */
export const IMAGE_ENCODE_QUALITY = 0.85;

/** 标准化失败错误：携带稳定业务错误码，供草稿状态机记录。 */
export class ImageNormalizeError extends Error {
  readonly code: string;
  readonly retryable: boolean;

  constructor(code: string, message: string, retryable = false) {
    super(message);
    this.name = "ImageNormalizeError";
    this.code = code;
    this.retryable = retryable;
  }
}

export interface NormalizedImage {
  blob: Blob;
  width: number;
  height: number;
  mimeType: string;
  fileSize: number;
  fileName: string;
}

/** 拒绝非 image/* 输入。 */
export function assertImageFileType(mimeType: string): void {
  if (!mimeType.startsWith("image/")) {
    throw new ImageNormalizeError("chat_image_format_invalid", "仅支持发送图片文件");
  }
}

/** 等比缩放：最长边不超过 maxEdge；不放大原图。 */
export function computeContainSize(width: number, height: number, maxEdge: number = IMAGE_MAX_EDGE): { width: number; height: number } {
  if (width <= 0 || height <= 0) return { width: Math.max(1, width), height: Math.max(1, height) };
  const longest = Math.max(width, height);
  if (longest <= maxEdge) return { width, height };
  const scale = maxEdge / longest;
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** 输出文件名：保留原名主体，后缀改为实际编码格式。 */
export function normalizedFileName(originalName: string, mimeType: string): string {
  const extension = mimeType === "image/webp" ? ".webp" : ".jpg";
  const base = (originalName || "image").replace(/\.[a-z0-9]+$/i, "").trim() || "image";
  return `${base}${extension}`;
}

/** 输出大小超限检查。 */
export function assertOutputSize(size: number, max: number = IMAGE_MAX_OUTPUT_BYTES): void {
  if (size > max) {
    throw new ImageNormalizeError("chat_image_normalize_failed", "图片压缩后仍超过大小限制，请更换图片");
  }
}

function canvasToBlob(canvas: HTMLCanvasElement, mimeType: string, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new ImageNormalizeError("chat_image_normalize_failed", "图片压缩失败，请重试", true));
    }, mimeType, quality);
  });
}

/**
 * 读取并标准化一张图片。
 * 解码失败/非图片输入抛 chat_image_format_invalid；canvas 编码失败或输出
 * 超限抛 chat_image_normalize_failed。
 */
export async function normalizeImageForUpload(file: File): Promise<NormalizedImage> {
  assertImageFileType(file.type);

  let bitmap: ImageBitmap;
  try {
    // imageOrientation: from-image 按 EXIF 方向修正后再绘制。
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new ImageNormalizeError("chat_image_format_invalid", "无法读取该图片，请更换图片");
  }

  try {
    const { width, height } = computeContainSize(bitmap.width, bitmap.height);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new ImageNormalizeError("chat_image_normalize_failed", "当前浏览器不支持图片压缩", false);
    context.drawImage(bitmap, 0, 0, width, height);

    // 优先 WebP；浏览器不支持时 toBlob 会回退为 PNG，此时改用 JPEG 重编码。
    let blob = await canvasToBlob(canvas, "image/webp", IMAGE_ENCODE_QUALITY);
    let mimeType = "image/webp";
    if (blob.type !== "image/webp") {
      blob = await canvasToBlob(canvas, "image/jpeg", IMAGE_ENCODE_QUALITY);
      mimeType = "image/jpeg";
    }
    assertOutputSize(blob.size);
    return { blob, width, height, mimeType, fileSize: blob.size, fileName: normalizedFileName(file.name, mimeType) };
  } finally {
    bitmap.close();
  }
}
