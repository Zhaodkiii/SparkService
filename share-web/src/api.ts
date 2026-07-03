export interface ApiEnvelope<T> {
  code: number;
  msg: string;
  data: T;
}

export type ShareBusinessType =
  | 'medical_case'
  | 'health_exam_report'
  | 'examination_report'
  | 'prescription'
  | 'medication_plan'
  | 'medicine_box';

export interface ShareAttachment {
  id: number;
  original_name?: string;
  mime_type?: string;
  file_size?: number;
  file_url?: string;
  download_url?: string;
}

export interface ShareTimelineEvent {
  id: string;
  kind: 'prescription' | 'medication' | 'examination' | 'symptom' | 'visit' | 'surgery' | 'follow_up' | 'meta';
  category?: string;
  title: string;
  detail: string;
  date: string;
  status_badge_text?: string | null;
  attachments?: ShareAttachment[];
  nested_medication_plans?: ShareMedicationPlan[];
  prescription?: SharePrescription;
  medication_plan?: ShareMedicationPlan;
  examination?: ShareExamination;
  symptom?: ShareSymptom;
  visit?: ShareVisit;
  surgery?: ShareSurgery;
  follow_up?: ShareFollowUp;
}

export interface ShareMember {
  id?: number;
  display_name: string;
  gender?: string;
  age_text?: string;
}

export interface SharePayloadBase {
  share: {
    share_code: string;
    business_type: ShareBusinessType;
    business_id: number;
    status: string;
    expires_at: string;
    title: string;
    share_url: string;
  };
  member: ShareMember;
  resource: Record<string, unknown>;
  download_app: {
    title: string;
    description: string;
    button_text: string;
    url: string;
  };
}

export interface SharePrescription {
  id: number;
  title: string;
  diagnosis?: string;
  prescribed_at?: string;
  status?: string;
  attachments?: ShareAttachment[];
}

export interface ShareMedicationPlan {
  id: number;
  drug_name?: string;
  dose_per_time?: string;
  frequency_text?: string;
  start_date?: string;
  status?: string;
  box_name?: string;
  attachments?: ShareAttachment[];
}

export interface ShareExamination {
  id: number;
  category?: string;
  sub_category?: string;
  item_name?: string;
  findings?: string;
  impression?: string;
  performed_at?: string;
  reported_at?: string;
  status?: number;
  attachments?: ShareAttachment[];
}

export interface ShareSymptom {
  id: number;
  name?: string;
  severity?: string;
  body_part?: string;
  notes?: string;
  started_at?: string;
  attachments?: ShareAttachment[];
}

export interface ShareVisit {
  id: number;
  visit_type?: string;
  visited_at?: string;
  department?: string;
  doctor_name?: string;
  visit_no?: string;
  notes?: string;
  attachments?: ShareAttachment[];
}

export interface ShareSurgery {
  id: number;
  procedure_name?: string;
  site?: string;
  performed_at?: string;
  surgeon?: string;
  notes?: string;
  attachments?: ShareAttachment[];
}

export interface ShareFollowUp {
  id: number;
  planned_at?: string;
  completed_at?: string;
  status?: string;
  method?: string;
  outcome?: string;
  next_action?: string;
  attachments?: ShareAttachment[];
}

export interface ShareCasePayload {
  share: SharePayloadBase['share'] & { business_type: 'medical_case' };
  member: ShareMember;
  case: ShareCaseResource;
  timeline: ShareTimelineEvent[];
  resource: ShareCaseResource;
  download_app: SharePayloadBase['download_app'];
}

export interface ShareCaseResource {
  id: number;
  title: string;
  record_type?: string;
  status?: number;
  status_badge_text?: string | null;
  diagnosis_summary?: string;
  hospital_name?: string;
  age_at_visit?: number | null;
  created_at?: string;
  updated_at?: string;
  attachments?: ShareAttachment[];
}

export interface ShareHealthExamPayload extends SharePayloadBase {
  share: SharePayloadBase['share'] & { business_type: 'health_exam_report' };
  report: {
    id: number;
    institution_name?: string;
    report_no?: string;
    exam_date?: string;
    exam_type?: number;
    summary?: string | null;
    source?: number;
    status?: number;
    created_at?: string;
    updated_at?: string;
    attachments?: ShareAttachment[];
    extra?: Record<string, unknown> | null;
  };
  med_exam_details: Array<{
    id: number;
    business_type: string;
    business_id: number;
    member: number;
    category?: string;
    sub_category?: string;
    item_name: string;
    item_code?: string;
    result_value?: string;
    unit?: string;
    reference_range?: string;
    flag?: string;
    result_at?: string;
    modality?: string;
    body_part?: string;
    diagnosis?: string | null;
    extra?: Record<string, unknown> | null;
    sort_order: number;
    updated_at?: string;
  }>;
  linked_medical_case?: {
    id: number;
    title?: string;
    hospital_name?: string;
    record_type?: string;
    status?: number;
    status_badge_text?: string | null;
    diagnosis_summary?: string;
    age_at_visit?: number | null;
    created_at?: string;
    updated_at?: string;
  } | null;
}

export interface ShareExaminationPayload extends SharePayloadBase {
  share: SharePayloadBase['share'] & { business_type: 'examination_report' };
  report: {
    id: number;
    medical_record?: number | null;
    category?: string;
    sub_category?: string;
    item_name?: string;
    performed_at?: string;
    reported_at?: string;
    organization_name?: string;
    department_name?: string;
    doctor_name?: string;
    findings?: string | null;
    impression?: string | null;
    source?: number;
    status?: number;
    created_at?: string;
    updated_at?: string;
    attachments?: ShareAttachment[];
    extra?: Record<string, unknown> | null;
  };
  med_exam_details: ShareHealthExamPayload['med_exam_details'];
  linked_medical_case?: ShareHealthExamPayload['linked_medical_case'] | null;
}

export interface SharePrescriptionPayload extends SharePayloadBase {
  share: SharePayloadBase['share'] & { business_type: 'prescription' };
  prescription: {
    id: number;
    title: string;
    diagnosis?: string;
    prescribed_at?: string;
    status?: string;
    attachments?: ShareAttachment[];
  };
  medication_plans: ShareMedicationPlan[];
  linked_medical_case?: ShareExaminationPayload['linked_medical_case'] | null;
}

export interface ShareMedicationPlanPayload extends SharePayloadBase {
  share: SharePayloadBase['share'] & { business_type: 'medication_plan' };
  medication_plan: ShareMedicationPlan;
  linked_medical_case?: SharePrescriptionPayload['linked_medical_case'] | null;
  linked_prescription?: {
    id: number;
    title: string;
    diagnosis?: string;
    prescribed_at?: string;
    status?: string;
    attachments?: ShareAttachment[];
  } | null;
  linked_medicine_box?: {
    id: number;
    medicine_name?: string;
    medicine_type?: string | null;
    brand_name?: string;
    dosage_form?: string;
    strength?: string;
    dose_unit?: string;
    total_quantity?: number | null;
    expire_date?: string | null;
    notes?: string;
    updated_at?: string;
  } | null;
  medication_records: Array<{
    id: number;
    scheduled_at?: string;
    taken_at?: string | null;
    status?: string;
    planned_dose?: string;
    actual_dose?: string;
    dose_sequence?: number;
    timezone?: string;
    notes?: string;
    updated_at?: string;
  }>;
}

export interface ShareMedicineBoxPayload extends SharePayloadBase {
  share: SharePayloadBase['share'] & { business_type: 'medicine_box' };
  medicine_box: {
    id: number;
    medicine_name: string;
    medicine_type?: string | null;
    brand_name?: string;
    dosage_form?: string;
    strength?: string;
    dose_unit?: string;
    total_quantity?: number | null;
    expire_date?: string | null;
    notes?: string;
    created_at?: string;
    updated_at?: string;
    attachments?: ShareAttachment[];
    extra?: Record<string, unknown> | null;
  };
  linked_medication_plans: ShareMedicationPlan[];
}

export type SharePublicPayload =
  | ShareCasePayload
  | ShareHealthExamPayload
  | ShareExaminationPayload
  | SharePrescriptionPayload
  | ShareMedicationPlanPayload
  | ShareMedicineBoxPayload;

const apiBase = import.meta.env.VITE_API_BASE_URL || '';

export async function loadSharePayload(shareCode: string): Promise<ApiEnvelope<SharePublicPayload>> {
  const response = await fetch(`${apiBase}/api/v1/medical/shares/public/${encodeURIComponent(shareCode)}/`, {
    headers: {
      Accept: 'application/json',
    },
  });
  const data = (await response.json()) as ApiEnvelope<SharePublicPayload>;
  return data;
}

export async function loadShareCase(shareCode: string): Promise<ApiEnvelope<ShareCasePayload>> {
  return loadSharePayload(shareCode) as Promise<ApiEnvelope<ShareCasePayload>>;
}

export function attachmentDisplayName(index: number): string {
  return `附件${index + 1}`;
}
