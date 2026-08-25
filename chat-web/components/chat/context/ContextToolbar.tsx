"use client";

import { ChevronDown, Database, FileText, Plus, UserRound, X } from "lucide-react";
import { useState } from "react";
import { useOptionalChatContext } from "@/context/ChatContextProvider";
import { useOptionalThreads } from "@/context/ThreadContext";
import type { HealthResourceType } from "@/types/context";

const RESOURCE_TYPES: Array<{ value: HealthResourceType; label: string }> = [
  { value: "health_exam_report", label: "体检报告" }, { value: "examination_report", label: "检查报告" },
  { value: "medical_case", label: "病例" }, { value: "medication_plan", label: "用药计划" }, { value: "member_key_indicator", label: "关键指标" },
];

export function ContextToolbar() {
  const context = useOptionalChatContext();
  const threads = useOptionalThreads();
  const [open, setOpen] = useState(false);
  const [fileId, setFileId] = useState("");
  const [resourceId, setResourceId] = useState("");
  const [resourceType, setResourceType] = useState<HealthResourceType>("health_exam_report");
  const [personaDraft, setPersonaDraft] = useState("");
  if (!context?.preferences) return null;
  const { preferences, draft, status, error, updatePreferences, addItem, removeItem } = context;
  const selectedThread = threads?.threads.find((thread) => thread.thread_id === threads.selectedThreadId);
  const toggleOpen = () => { setPersonaDraft(preferences.persona?.custom_text ?? ""); setOpen((value) => !value); };
  const addFile = () => { const value = fileId.trim(); if (!value) return; addItem({ key: `attachment:file:${value}`, kind: "attachment", fileId: value, title: `文件 ${value}`, status: "ready" }); setFileId(""); };
  const addResource = () => { const id = resourceId.trim(); if (!id || !selectedThread?.member_id) return; addItem({ key: `health:${resourceType}:${id}`, kind: "health_resource", resourceType, resourceId: id, memberId: selectedThread.member_id, title: RESOURCE_TYPES.find((item) => item.value === resourceType)?.label ?? resourceType, status: "ready" }); setResourceId(""); };
  return <section className="context-toolbar" aria-label="对话上下文">
    <button className="composer-icon" type="button" onClick={toggleOpen} aria-expanded={open} aria-label="添加上下文" title="添加资料与上下文"><Plus size={17} /></button>
    <button className="context-trigger" type="button" onClick={toggleOpen} aria-expanded={open}><Database size={14} /><span>{draft.items.length ? `${draft.items.length} 项上下文` : "上下文"}</span><ChevronDown size={12} /></button>
    {draft.items.slice(0, 2).map((item) => <button key={item.key} className="context-chip" type="button" onClick={() => removeItem(item.key)} aria-label={`移除${item.title}`}><span>{item.title}</span><X size={11} /></button>)}
    {draft.items.length > 2 && <span className="context-count">+{draft.items.length - 2}</span>}
    {open && <div className="context-panel" role="dialog" aria-label="上下文设置">
      <header><div><strong>本轮上下文</strong><span>{status === "saving" ? "正在保存" : error ?? `${draft.items.length}/16 项`}</span></div><button type="button" aria-label="关闭上下文设置" onClick={() => setOpen(false)}><X size={16} /></button></header>
      <div className="context-panel__section"><div className="context-section-title"><UserRound size={15} /><strong>回答偏好</strong></div><label>自定义回答风格<textarea value={personaDraft} maxLength={4000} onChange={(event) => setPersonaDraft(event.target.value)} placeholder="例如：简洁、审慎地解释" /></label><div className="context-inline"><button type="button" onClick={() => void updatePreferences({ persona: { ...preferences.persona, custom_text: personaDraft.trim() } })}>保存风格</button><button type="button" className="secondary" onClick={() => void updatePreferences({ language: preferences.language === "zh-CN" ? "en-US" : "zh-CN" })}>{preferences.language === "zh-CN" ? "中文" : "English"}</button></div></div>
      <div className="context-panel__section"><div className="context-section-title"><FileText size={15} /><strong>文件引用</strong></div><div className="context-inline"><input value={fileId} onChange={(event) => setFileId(event.target.value)} placeholder="ManagedFile ID" aria-label="文件 ID" /><button type="button" onClick={addFile}>添加</button></div><small>服务端会校验文件访问权限。</small></div>
      <div className="context-panel__section"><div className="context-section-title"><Database size={15} /><strong>健康资源</strong></div><div className="context-resource-row"><select value={resourceType} onChange={(event) => setResourceType(event.target.value as HealthResourceType)} aria-label="健康资源类型">{RESOURCE_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><input value={resourceId} onChange={(event) => setResourceId(event.target.value)} placeholder={selectedThread?.member_id ? "资源 ID" : "当前对话未绑定成员"} aria-label="资源 ID" /><button type="button" onClick={addResource} disabled={!selectedThread?.member_id}>添加</button></div></div>
      <button className="context-panel__done" type="button" onClick={() => setOpen(false)}>完成</button>
    </div>}
  </section>;
}
