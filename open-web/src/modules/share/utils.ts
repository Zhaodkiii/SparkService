import type {
  ShareBusinessType,
  ShareCasePayload,
  ShareErrorKind,
  ShareExaminationPayload,
  ShareHealthExamPayload,
  ShareMedicationPlanPayload,
  ShareMedicineBoxPayload,
  SharePrescriptionPayload,
  SharePublicPayload,
  ShareTimelineEvent,
} from './types';

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

const dayFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

export function formatDate(value?: string | null) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return dateFormatter.format(parsed);
}

export function formatDay(value?: string | null) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return dayFormatter.format(parsed);
}

export function joinText(values: Array<string | undefined | null>) {
  return values
    .map((value) => value?.trim())
    .filter((value): value is string => Boolean(value))
    .join(' · ');
}

export function attachmentDisplayName(index: number): string {
  return `附件${index + 1}`;
}

export function kindLabel(kind: ShareTimelineEvent['kind']) {
  switch (kind) {
    case 'prescription':
      return '处';
    case 'medication':
      return '药';
    case 'examination':
      return '检';
    case 'symptom':
      return '症';
    case 'visit':
      return '诊';
    case 'surgery':
      return '术';
    case 'follow_up':
      return '访';
    case 'meta':
      return '信';
    default:
      return '医';
  }
}

export function resourceKindLabel(kind: string) {
  switch (kind) {
    case 'medical_case':
      return '病例';
    case 'health_exam_report':
      return '体检';
    case 'examination_report':
      return '检查';
    case 'prescription':
      return '处方';
    case 'medication_plan':
      return '计划';
    case 'medicine_box':
      return '药箱';
    default:
      return '医疗';
  }
}

export function kindTitle(kind: ShareTimelineEvent['kind']) {
  switch (kind) {
    case 'prescription':
      return '处方';
    case 'medication':
      return '服药计划';
    case 'examination':
      return '检查报告';
    case 'symptom':
      return '症状记录';
    case 'visit':
      return '就诊信息';
    case 'surgery':
      return '手术记录';
    case 'follow_up':
      return '随访记录';
    case 'meta':
      return '病例信息';
    default:
      return '记录';
  }
}

export function kindClass(kind: ShareTimelineEvent['kind']) {
  return `kind-${kind}`;
}

export function openAttachment(file: { download_url?: string; file_url?: string }) {
  const url = file.download_url || file.file_url;
  if (!url) return;
  window.open(url, '_blank', 'noopener,noreferrer');
}

export function getResourceAttachments(payload: SharePublicPayload) {
  if (isBusinessType(payload, 'medical_case')) return payload.case.attachments ?? [];
  if (isBusinessType(payload, 'health_exam_report')) return payload.report.attachments ?? [];
  if (isBusinessType(payload, 'examination_report')) return payload.report.attachments ?? [];
  if (isBusinessType(payload, 'prescription')) return payload.prescription.attachments ?? [];
  if (isBusinessType(payload, 'medication_plan')) return payload.medication_plan.attachments ?? [];
  if (isBusinessType(payload, 'medicine_box')) return payload.medicine_box.attachments ?? [];
  return [];
}

export function getResourceTitle(payload: SharePublicPayload) {
  if (isBusinessType(payload, 'medical_case')) {
    return payload.case.title || payload.share.title || '公开分享';
  }
  if (isBusinessType(payload, 'health_exam_report')) {
    return payload.report.institution_name || payload.share.title || '公开分享';
  }
  if (isBusinessType(payload, 'examination_report')) {
    return (
      payload.report.item_name ||
      payload.report.organization_name ||
      payload.share.title ||
      '公开分享'
    );
  }
  if (isBusinessType(payload, 'prescription')) {
    return payload.prescription.title || payload.share.title || '公开分享';
  }
  if (isBusinessType(payload, 'medication_plan')) {
    return payload.medication_plan.drug_name || payload.share.title || '公开分享';
  }
  if (isBusinessType(payload, 'medicine_box')) {
    return payload.medicine_box.medicine_name || payload.share.title || '公开分享';
  }
  return '公开分享';
}

export function getResourceStatusBadge(payload: SharePublicPayload) {
  if (isBusinessType(payload, 'medical_case')) {
    return payload.case.status_badge_text || '';
  }
  if (isBusinessType(payload, 'medicine_box')) {
    return payload.medicine_box.total_quantity == null
      ? ''
      : `库存 ${payload.medicine_box.total_quantity}`;
  }
  return '';
}

export function getResourceSummaryLines(payload: SharePublicPayload): string[] {
  if (isBusinessType(payload, 'medical_case')) {
    return [
      payload.member.display_name,
      payload.case.hospital_name,
      payload.case.record_type,
      payload.case.created_at ? formatDay(payload.case.created_at) : '',
    ].filter(Boolean) as string[];
  }
  if (isBusinessType(payload, 'health_exam_report')) {
    return [
      payload.member.display_name,
      payload.report.institution_name,
      payload.report.report_no,
      payload.report.exam_date ? formatDay(payload.report.exam_date) : '',
    ].filter(Boolean) as string[];
  }
  if (isBusinessType(payload, 'examination_report')) {
    const examDate = payload.report.reported_at || payload.report.performed_at;
    return [
      payload.member.display_name,
      payload.report.organization_name,
      payload.report.category,
      examDate ? formatDate(examDate) : '',
    ].filter(Boolean) as string[];
  }
  if (isBusinessType(payload, 'prescription')) {
    return [
      payload.member.display_name,
      payload.prescription.diagnosis,
      payload.prescription.prescribed_at
        ? formatDate(payload.prescription.prescribed_at)
        : '',
    ].filter(Boolean) as string[];
  }
  if (isBusinessType(payload, 'medication_plan')) {
    return [
      payload.member.display_name,
      payload.medication_plan.dose_per_time,
      payload.medication_plan.frequency_text,
      payload.medication_plan.start_date
        ? formatDay(payload.medication_plan.start_date)
        : '',
    ].filter(Boolean) as string[];
  }
  if (isBusinessType(payload, 'medicine_box')) {
    return [
      payload.member.display_name,
      payload.medicine_box.brand_name,
      payload.medicine_box.dosage_form,
      payload.medicine_box.expire_date ? formatDay(payload.medicine_box.expire_date) : '',
    ].filter(Boolean) as string[];
  }
  return [];
}

export type NonCaseSharePayload =
  | ShareHealthExamPayload
  | ShareExaminationPayload
  | SharePrescriptionPayload
  | ShareMedicationPlanPayload
  | ShareMedicineBoxPayload;

export function asNonCasePayload(payload: SharePublicPayload): NonCaseSharePayload | null {
  if (isBusinessType(payload, 'medical_case')) return null;
  return payload;
}

export function classifyShareError(err: unknown): { kind: ShareErrorKind; title: string; description: string } {
  const message = err instanceof Error ? err.message : '';
  if (message.includes('expired') || message.includes('revoked')) {
    return {
      kind: 'expired',
      title: '链接已失效',
      description: '分享已过期或已撤销，请下载 App 继续查看。',
    };
  }
  if (message === 'not_found') {
    return {
      kind: 'unavailable',
      title: '内容不可用',
      description: '当前分享无法打开，请下载 App 查看完整内容。',
    };
  }
  if (message.includes('Network Error') || message === 'request_failed') {
    return {
      kind: 'network',
      title: '链接已失效',
      description: '网络不可用或链接已过期，请下载 App 查看完整内容。',
    };
  }
  return {
    kind: 'unavailable',
    title: '内容不可用',
    description: '当前分享无法打开，请下载 App 查看完整内容。',
  };
}

export function isBusinessType<T extends ShareBusinessType>(
  payload: SharePublicPayload,
  type: T,
): payload is Extract<SharePublicPayload, { share: { business_type: T } }> {
  return payload.share.business_type === type;
}

export function asCasePayload(payload: SharePublicPayload): ShareCasePayload | null {
  return isBusinessType(payload, 'medical_case') ? payload : null;
}
