"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { Download, Minus, Plus, RotateCcw, X } from "lucide-react";

export type AttachmentPreviewItem = {
  url: string;
  filename: string;
  mime_type?: string | null;
  kind?: "image" | "document";
};

type AttachmentPreviewContextValue = {
  open: (item: AttachmentPreviewItem) => void;
  close: () => void;
};

const AttachmentPreviewContext = createContext<AttachmentPreviewContextValue | null>(null);

const MIN_SCALE = 0.5;
const MAX_SCALE = 3;
const SCALE_STEP = 0.25;

function extensionOf(filename: string): string {
  const parts = filename.split(".");
  return parts.length > 1 ? parts.pop()!.toLowerCase() : "";
}

export function isImagePreviewItem(item: AttachmentPreviewItem): boolean {
  if (item.kind === "image") return true;
  const mime = (item.mime_type ?? "").toLowerCase();
  if (mime.startsWith("image/")) return true;
  return ["jpg", "jpeg", "png", "webp", "gif", "heic", "bmp", "svg"].includes(extensionOf(item.filename));
}

export function isPdfPreviewItem(item: AttachmentPreviewItem): boolean {
  const mime = (item.mime_type ?? "").toLowerCase();
  return mime === "application/pdf" || extensionOf(item.filename) === "pdf";
}

function clampScale(value: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));
}

function AttachmentPreviewModal({ item, onClose }: { item: AttachmentPreviewItem; onClose: () => void }) {
  const [scale, setScale] = useState(1);
  const [failed, setFailed] = useState(false);
  const image = isImagePreviewItem(item);
  const pdf = !image && isPdfPreviewItem(item);

  useEffect(() => {
    setScale(1);
    setFailed(false);
  }, [item.url, item.filename]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "+" || event.key === "=") setScale((current) => clampScale(current + SCALE_STEP));
      if (event.key === "-") setScale((current) => clampScale(current - SCALE_STEP));
      if (event.key === "0") setScale(1);
    };
    window.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  const zoomIn = () => setScale((current) => clampScale(current + SCALE_STEP));
  const zoomOut = () => setScale((current) => clampScale(current - SCALE_STEP));
  const resetZoom = () => setScale(1);

  return (
    <div className="attachment-preview" role="dialog" aria-modal="true" aria-labelledby="attachment-preview-title">
      <button type="button" className="attachment-preview__scrim" aria-label="关闭预览" onClick={onClose} />
      <div className="attachment-preview__panel">
        <header className="attachment-preview__head">
          <div className="attachment-preview__title-wrap">
            <h2 id="attachment-preview-title">{item.filename}</h2>
            <p>{image ? "图片预览" : pdf ? "PDF 预览" : "附件预览"}</p>
          </div>
          <div className="attachment-preview__tools">
            {(image || pdf) ? (
              <>
                <button type="button" className="attachment-preview__tool" aria-label="缩小" onClick={zoomOut} disabled={scale <= MIN_SCALE}>
                  <Minus size={16} />
                </button>
                <span className="attachment-preview__scale">{Math.round(scale * 100)}%</span>
                <button type="button" className="attachment-preview__tool" aria-label="放大" onClick={zoomIn} disabled={scale >= MAX_SCALE}>
                  <Plus size={16} />
                </button>
                <button type="button" className="attachment-preview__tool" aria-label="重置缩放" onClick={resetZoom}>
                  <RotateCcw size={16} />
                </button>
              </>
            ) : null}
            <a className="attachment-preview__tool" href={item.url} download={item.filename} aria-label={`下载 ${item.filename}`}>
              <Download size={16} />
            </a>
            <button type="button" className="attachment-preview__tool" aria-label="关闭" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </header>
        <div
          className="attachment-preview__body"
          onWheel={(event) => {
            if (!image && !pdf) return;
            if (!event.ctrlKey && !event.metaKey) return;
            event.preventDefault();
            setScale((current) => clampScale(current + (event.deltaY < 0 ? SCALE_STEP : -SCALE_STEP)));
          }}
        >
          {failed ? (
            <div className="attachment-preview__fallback" role="alert">
              <p>附件预览加载失败。</p>
              <a href={item.url} target="_blank" rel="noreferrer noopener">在新窗口打开</a>
            </div>
          ) : image ? (
            <div className="attachment-preview__stage" style={{ transform: `scale(${scale})` }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={item.url} alt={item.filename} onError={() => setFailed(true)} />
            </div>
          ) : pdf ? (
            <div className="attachment-preview__stage attachment-preview__stage--pdf" style={{ transform: `scale(${scale})` }}>
              <iframe src={item.url} title={item.filename} onError={() => setFailed(true)} />
            </div>
          ) : (
            <div className="attachment-preview__fallback">
              <p>该文件类型暂不支持内嵌预览。</p>
              <a href={item.url} target="_blank" rel="noreferrer noopener">在新窗口打开</a>
              <a href={item.url} download={item.filename}>下载文件</a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function AttachmentPreviewProvider({ children }: { children: ReactNode }) {
  const [item, setItem] = useState<AttachmentPreviewItem | null>(null);
  const close = useCallback(() => setItem(null), []);
  const open = useCallback((next: AttachmentPreviewItem) => {
    if (!next.url) return;
    setItem(next);
  }, []);
  const value = useMemo(() => ({ open, close }), [open, close]);

  return (
    <AttachmentPreviewContext.Provider value={value}>
      {children}
      {item ? <AttachmentPreviewModal item={item} onClose={close} /> : null}
    </AttachmentPreviewContext.Provider>
  );
}

export function useAttachmentPreview(): AttachmentPreviewContextValue {
  const context = useContext(AttachmentPreviewContext);
  if (!context) {
    throw new Error("useAttachmentPreview must be used within AttachmentPreviewProvider");
  }
  return context;
}

/** 可选 hook：Provider 未挂载时静默降级，便于渐进接入。 */
export function useOptionalAttachmentPreview(): AttachmentPreviewContextValue | null {
  return useContext(AttachmentPreviewContext);
}

export function openPreviewOnEnter(callback: () => void) {
  return (event: ReactKeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      callback();
    }
  };
}
