"use client";

import { useState } from "react";

export function MemoryEntryEditor({
  onCancel,
  onSave,
  saving,
  error,
}: {
  onCancel: () => void;
  onSave: (draft: { title: string; content: string }) => void;
  saving?: boolean;
  error?: string | null;
}) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  return (
    <div className="knowledge-modal" role="dialog" aria-modal="true" aria-labelledby="memory-editor-title">
      <form
        className="knowledge-modal__card"
        onSubmit={(event) => {
          event.preventDefault();
          onSave({ title, content });
        }}
      >
        <header>
          <h2 id="memory-editor-title">新建记忆</h2>
          <button type="button" className="secondary" onClick={onCancel}>关闭</button>
        </header>
        <label>标题<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={128} /></label>
        <label>内容<textarea value={content} onChange={(event) => setContent(event.target.value)} maxLength={240} rows={4} required /></label>
        {error && <p className="knowledge-error">{error}</p>}
        <footer>
          <button type="button" className="secondary" onClick={onCancel}>取消</button>
          <button type="submit" disabled={saving || !content.trim()}>{saving ? "保存中…" : "创建"}</button>
        </footer>
      </form>
    </div>
  );
}
