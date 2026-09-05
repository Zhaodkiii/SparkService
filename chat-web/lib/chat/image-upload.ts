/**
 * OSS 直传（CHAT-WEB-029 §6.1）：XMLHttpRequest PUT 上传标准化图片到
 * 服务端签发的 upload_url，监听 upload.onprogress 汇报百分比。
 * 不引入任何 OSS SDK 依赖。
 */

/** 直传失败错误：网络错误与 5xx 可重试，4xx 不可重试。 */
export class ImageUploadError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly httpStatus?: number;

  constructor(code: string, message: string, retryable: boolean, httpStatus?: number) {
    super(message);
    this.name = "ImageUploadError";
    this.code = code;
    this.retryable = retryable;
    this.httpStatus = httpStatus;
  }
}

/**
 * PUT 上传并汇报进度。
 * @param signal 可选取消信号；取消时 Promise 以 chat_image_upload_cancelled 拒绝。
 */
export function uploadWithProgress(
  url: string,
  headers: Record<string, string>,
  blob: Blob,
  onProgress: (percent: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    const onAbort = () => xhr.abort();
    if (signal) {
      if (signal.aborted) {
        reject(new ImageUploadError("chat_image_upload_cancelled", "上传已取消", false));
        return;
      }
      signal.addEventListener("abort", onAbort, { once: true });
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    };
    xhr.onload = () => {
      signal?.removeEventListener("abort", onAbort);
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100);
        resolve();
      } else {
        reject(new ImageUploadError("chat_image_upload_failed", "图片上传失败，请重试", xhr.status === 0 || xhr.status >= 500, xhr.status));
      }
    };
    xhr.onerror = () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new ImageUploadError("chat_image_upload_failed", "网络异常，图片上传失败", true));
    };
    xhr.onabort = () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new ImageUploadError("chat_image_upload_cancelled", "上传已取消", false));
    };

    xhr.open("PUT", url);
    for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value);
    xhr.send(blob);
  });
}
