"use client";

import type { KeyboardEvent, MouseEvent } from "react";
import { AlertTriangle, FileSearch, HeartHandshake, ShieldAlert, Sparkles } from "lucide-react";
import { asString, BlockShell, blockValue, blockValueObject, CardRow, ReadOnlyCard } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";
import type { HealthResourceReference } from "@/types/medical-resource";

function asIdentifier(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return asString(value);
}

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

export function HealthResourceReferenceBlock({ block, onHealthResourceOpen }: BlockRenderProps) {
  const value = blockValueObject(block);
  const resourceType = asString(value.resource_type) ?? asString(value.resourceType) ?? asString(value.type) ?? "health_resource";
  const resourceId = asIdentifier(value.resource_id) ?? asIdentifier(value.resourceId);
  const memberId = asIdentifier(value.member_id) ?? asIdentifier(value.memberId);
  const refIndex = asIdentifier(value.ref_index) ?? asIdentifier(value.refIndex);
  const typeLabel = resourceType === "examination_report"
    ? "检查报告"
    : resourceType === "health_exam_report"
      ? "体检报告"
      : resourceType === "medical_case"
        ? "病例"
        : resourceType === "medication_plan"
          ? "用药计划"
          : resourceType === "medicine_box" || resourceType === "medicine-box"
            ? "药箱"
          : "健康资料";
  const title = asString(value.title) ?? `${typeLabel}${resourceId ? ` #${resourceId}` : ""}`;
  const date = asString(value.performed_at) ?? asString(value.exam_date) ?? asString(value.date);
  const organization = asString(value.hospital_name) ?? asString(value.organization) ?? asString(value.hospital);
  const summary = asString(value.summary) ?? asString(value.description) ?? asString(value.detail);
  const source = asString(value.source) ?? asString(value.url);
  const metadata = [date, organization].filter(Boolean).join(" · ");
  const reference: HealthResourceReference | null = resourceId && memberId && Number.isInteger(Number(resourceId)) && Number.isInteger(Number(memberId))
    ? { resourceType, resourceId: Number(resourceId), memberId: Number(memberId), refIndex: refIndex ? Number(refIndex) : undefined }
    : null;
  const open = (event: MouseEvent<HTMLElement> | KeyboardEvent<HTMLElement>) => {
    if (!reference) return;
    event.stopPropagation();
    onHealthResourceOpen?.(reference);
  };

  return <BlockShell block={block}>
    <article className="health-resource-reference-card" role={reference ? "button" : undefined} tabIndex={reference ? 0 : undefined} aria-haspopup={reference ? "dialog" : undefined} aria-label={`${typeLabel}：${title}`} onClick={reference ? open : undefined} onKeyDown={reference ? (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(event); } } : undefined}>
      <div className="health-resource-reference-card__icon" aria-hidden="true"><FileSearch size={19} /></div>
      <div className="health-resource-reference-card__content">
        <div className="health-resource-reference-card__eyebrow">
          <span>{typeLabel}</span>
          {refIndex ? <span className="health-resource-reference-card__index">第 {refIndex} 项</span> : null}
        </div>
        <strong className="health-resource-reference-card__title">{title}</strong>
        {metadata ? <span className="health-resource-reference-card__meta">{metadata}</span> : null}
        {summary ? <span className="health-resource-reference-card__summary">{summary}</span> : null}
        {!summary && resourceId ? <span className="health-resource-reference-card__meta">资料编号：{resourceId}{memberId ? ` · 成员 ${memberId}` : ""}</span> : null}
        {source ? <CardRow label="来源" value={source} /> : null}
      </div>
    </article>
  </BlockShell>;
}

export function ChatGuideCardBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const title = asString(value.title) ?? "使用引导";
  const text = asString(value.text) ?? asString(value.description);
  return <BlockShell block={block}><ReadOnlyCard title={title}><HeartHandshake size={14} />{text && <p>{text}</p>}</ReadOnlyCard></BlockShell>;
}
