"use client";

import { useEffect, useState } from "react";
import { Download, FileSearch, X } from "lucide-react";
import { useOptionalAuth } from "@/context/AuthContext";
import { SparkMedicalResourceApi } from "@/lib/api/medical-resource-api";
import type { HealthResourceReference, MedicalExamDetail, MedicalResourceAttachment, MedicalResourceRecord } from "@/types/medical-resource";

function text(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : "—";
}

function formatDate(value: unknown): string {
  if (typeof value !== "string" || !value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

function typeLabel(type: string): string {
  return ({ examination_report: "检查报告", health_exam_report: "体检报告", medical_case: "病例", medication_plan: "用药计划", medicine_box: "药箱", "medicine-box": "药箱", member_key_indicator: "关键指标" } as Record<string, string>)[type] ?? "健康资料";
}

function attachmentUrl(item: MedicalResourceAttachment): string | null {
  return item.download_url ?? item.file_url ?? item.url ?? null;
}

function isImageAttachment(item: MedicalResourceAttachment, url: string): boolean {
  if (item.mime_type?.toLowerCase().startsWith("image/")) return true;
  return /\.(avif|gif|jpe?g|png|webp)(?:[?#].*)?$/i.test(url);
}

function Field({ label, value }: { label: string; value: unknown }) {
  return <div className="health-resource-detail__field"><span>{label}</span><strong>{text(value)}</strong></div>;
}

function Attachments({ attachments }: { attachments: MedicalResourceAttachment[] }) {
  if (!attachments.length) return null;
  return <section className="health-resource-detail__section"><div className="health-resource-detail__section-head"><h3>附件</h3><span>{attachments.length} 个</span></div><div className="health-resource-detail__attachments">
    {attachments.map((item, index) => {
      const url = attachmentUrl(item);
      const name = item.original_name ?? item.filename ?? `附件${index + 1}`;
      if (!url) return <span key={String(item.id ?? index)}><FileSearch size={14} />{name}</span>;
      if (isImageAttachment(item, url)) return <figure className="health-resource-detail__image-attachment" key={String(item.id ?? index)}><a href={url} target="_blank" rel="noreferrer noopener" aria-label={`查看图片：${name}`}><img src={url} alt={name} loading="lazy" /></a><figcaption>{name}</figcaption></figure>;
      return <a key={String(item.id ?? index)} href={url} target="_blank" rel="noreferrer noopener"><Download size={14} />{name}<span className="health-resource-detail__download-hint">下载</span></a>;
    })}
  </div></section>;
}

function ExamDetails({ details }: { details: MedicalExamDetail[] }) {
  if (!details.length) return <p className="health-resource-detail__empty">暂无检查明细。</p>;
  return <div className="health-resource-detail__detail-list">{[...details].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)).map((item) => <article className={`health-resource-detail__detail-row${item.flag ? " health-resource-detail__detail-row--abnormal" : ""}`} key={item.id}>
    <strong>{text(item.item_name)}</strong>
    <span>{[item.category, item.sub_category].filter(Boolean).join(" · ") || "—"}</span>
    <span>{[item.result_value, item.unit].filter(Boolean).join(" ") || "—"}</span>
    <span>{item.reference_range ? `参考：${item.reference_range}` : ""}</span>
    {item.flag ? <em>{item.flag}</em> : null}
  </article>)}</div>;
}

function DetailContent({ reference, record, details }: { reference: HealthResourceReference; record: MedicalResourceRecord; details: MedicalExamDetail[] }) {
  const attachments = Array.isArray(record.attachments) ? record.attachments : [];
  if (reference.resourceType === "examination_report") return <>
    <section className="health-resource-detail__section"><div className="health-resource-detail__grid"><Field label="检查项目" value={record.item_name} /><Field label="检查分类" value={[record.category, record.sub_category].filter(Boolean).join(" · ")} /><Field label="检查机构" value={record.organization_name} /><Field label="科室" value={record.department_name} /><Field label="医生" value={record.doctor_name} /><Field label="报告时间" value={formatDate(record.reported_at ?? record.performed_at)} /><Field label="状态" value={record.status} /></div></section>
    <section className="health-resource-detail__section"><div className="health-resource-detail__section-head"><h3>检查结论</h3></div><p className="health-resource-detail__prose">{text(record.impression)}</p><h3 className="health-resource-detail__subhead">检查所见</h3><p className="health-resource-detail__prose">{text(record.findings)}</p></section>
    <section className="health-resource-detail__section"><div className="health-resource-detail__section-head"><h3>检查明细</h3><span>{details.length} 项</span></div><ExamDetails details={details} /></section>
    <Attachments attachments={attachments} />
  </>;

  if (reference.resourceType === "health_exam_report") return <>
    <section className="health-resource-detail__section"><div className="health-resource-detail__grid"><Field label="体检机构" value={record.institution_name} /><Field label="报告编号" value={record.report_no} /><Field label="体检日期" value={formatDate(record.exam_date)} /><Field label="状态" value={record.status} /></div></section>
    <section className="health-resource-detail__section"><div className="health-resource-detail__section-head"><h3>报告摘要</h3></div><p className="health-resource-detail__prose">{text(record.summary)}</p></section>
    <section className="health-resource-detail__section"><div className="health-resource-detail__section-head"><h3>体检明细</h3><span>{details.length} 项</span></div><ExamDetails details={details} /></section>
    <Attachments attachments={attachments} />
  </>;

  if (reference.resourceType === "medicine_box" || reference.resourceType === "medicine-box") return <>
    <section className="health-resource-detail__section"><div className="health-resource-detail__grid"><Field label="药品名称" value={record.medicine_name} /><Field label="品牌" value={record.brand_name} /><Field label="剂型" value={record.dosage_form} /><Field label="规格" value={record.strength} /><Field label="库存" value={record.total_quantity} /><Field label="有效期" value={formatDate(record.expire_date)} /><Field label="药箱类型" value={record.medicine_type} /><Field label="药箱编号" value={record.id} /></div></section>
    <section className="health-resource-detail__section"><div className="health-resource-detail__section-head"><h3>备注</h3></div><p className="health-resource-detail__prose">{text(record.notes)}</p></section>
    <Attachments attachments={attachments} />
  </>;

  return <section className="health-resource-detail__section"><div className="health-resource-detail__grid"><Field label="资源类型" value={typeLabel(reference.resourceType)} /><Field label="资源编号" value={reference.resourceId} /><Field label="成员编号" value={reference.memberId} /><Field label="更新时间" value={formatDate(record.updated_at)} /></div><p className="health-resource-detail__prose">{text(record.summary ?? record.description ?? record.notes ?? record.diagnosis_summary)}</p><Attachments attachments={attachments} /></section>;
}

export function HealthResourceDetailDialog({ reference, onClose }: { reference: HealthResourceReference | null; onClose: () => void }) {
  const auth = useOptionalAuth();
  const [record, setRecord] = useState<MedicalResourceRecord | null>(null);
  const [details, setDetails] = useState<MedicalExamDetail[]>([]);
  const [status, setStatus] = useState<"loading" | "loaded" | "failed">("loading");
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!reference) return;
    let cancelled = false;
    setStatus("loading"); setRecord(null); setDetails([]);
    if (!auth || auth.status !== "authenticated") { setStatus("failed"); return; }
    const api = new SparkMedicalResourceApi(auth.client);
    Promise.all([api.getResource(reference), api.getExamDetails(reference)]).then(([nextRecord, nextDetails]) => {
      if (cancelled) return;
      setRecord(nextRecord); setDetails(nextDetails); setStatus("loaded");
    }).catch(() => { if (!cancelled) setStatus("failed"); });
    return () => { cancelled = true; };
  }, [auth, reference, reloadToken]);

  useEffect(() => {
    if (!reference) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.body.style.overflow = previous; document.removeEventListener("keydown", onKeyDown); };
  }, [onClose, reference]);

  if (!reference) return null;
  const title = record ? text(record.item_name ?? record.institution_name ?? record.title ?? `${typeLabel(reference.resourceType)} #${reference.resourceId}`) : `${typeLabel(reference.resourceType)} #${reference.resourceId}`;
  return <div className="health-resource-detail-overlay" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
    <section className="health-resource-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="health-resource-detail-title">
      <header className="health-resource-detail-dialog__header"><div><p className="health-resource-detail-dialog__eyebrow">{typeLabel(reference.resourceType)}</p><h2 id="health-resource-detail-title">{title}</h2><p>资源编号：{reference.resourceId}</p></div><button type="button" className="health-resource-detail-dialog__close" aria-label="关闭详情" onClick={onClose}><X size={18} /></button></header>
      <div className="health-resource-detail-dialog__scroll">{status === "loading" ? <div className="health-resource-detail__state" aria-busy="true">正在加载报告详情…</div> : status === "failed" ? <div className="health-resource-detail__state" role="alert"><strong>报告详情加载失败</strong><p>请检查登录状态或稍后重试。</p><button type="button" onClick={() => setReloadToken((value) => value + 1)}>重新加载</button></div> : record ? <DetailContent reference={reference} record={record} details={details} /> : null}</div>
    </section>
  </div>;
}
