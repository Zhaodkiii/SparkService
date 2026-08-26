"use client";

import { AlertTriangle, HeartHandshake, ShieldAlert, Sparkles } from "lucide-react";
import { asString, BlockShell, blockValue, blockValueObject, CardRow, ReadOnlyCard } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";

export function ErrorBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const message = asString(blockValue(block)) ?? asString(value.message) ?? asString(value.detail) ?? "出现错误";
  return <BlockShell block={block}><div className="block block--notice" role="alert"><AlertTriangle size={14} /><strong>出现错误</strong><p>{message}</p></div></BlockShell>;
}

export function MedicalRiskNoticeBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const text = asString(blockValue(block)) ?? asString(value.text) ?? asString(value.message) ?? "请注意，此信息不构成医疗建议。";
  return <BlockShell block={block}><div className="block block--notice"><ShieldAlert size={14} /><strong>医疗风险提示</strong><p>{text}</p></div></BlockShell>;
}

export function MedicalDisclaimerCardBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const text = asString(blockValue(block)) ?? asString(value.text) ?? asString(value.message) ?? "内容仅供参考，重要医疗决定请咨询专业医生。";
  return <BlockShell block={block}><ReadOnlyCard title="医疗免责声明"><p>{text}</p></ReadOnlyCard></BlockShell>;
}

export function AssistantStatusCardBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const status = asString(value.type) ?? asString(value.message) ?? asString(value.text) ?? "处理中";
  return <BlockShell block={block}><div className="block block--status" role="status"><Sparkles size={14} /><span>{status}</span></div></BlockShell>;
}

export function HealthResourceReferenceBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const title = asString(value.title) ?? "健康资料引用";
  const source = asString(value.source) ?? asString(value.url);
  return <BlockShell block={block}><ReadOnlyCard title={title}>{source && <CardRow label="来源" value={source} />}</ReadOnlyCard></BlockShell>;
}

export function ChatGuideCardBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const title = asString(value.title) ?? "使用引导";
  const text = asString(value.text) ?? asString(value.description);
  return <BlockShell block={block}><ReadOnlyCard title={title}><HeartHandshake size={14} />{text && <p>{text}</p>}</ReadOnlyCard></BlockShell>;
}