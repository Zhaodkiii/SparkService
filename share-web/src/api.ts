export interface ApiEnvelope<T> {
  code: number;
  msg: string;
  data: T;
}

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
  share: {
    share_code: string;
    business_type: string;
    business_id: number;
    status: string;
    expires_at: string;
    title: string;
    share_url: string;
  };
  member: {
    id?: number;
    display_name: string;
    gender?: string;
    age_text?: string;
  };
  case: {
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
  };
  timeline: ShareTimelineEvent[];
  download_app: {
    title: string;
    description: string;
    button_text: string;
    url: string;
  };
}

const apiBase = import.meta.env.VITE_API_BASE_URL || '';

export async function loadShareCase(shareCode: string): Promise<ApiEnvelope<ShareCasePayload>> {
  const response = await fetch(`${apiBase}/api/v1/medical/shares/public/${encodeURIComponent(shareCode)}/`, {
    headers: {
      Accept: 'application/json',
    },
  });
  const data = (await response.json()) as ApiEnvelope<ShareCasePayload>;
  return data;
}

export function attachmentDisplayName(index: number): string {
  return `附件${index + 1}`;
}
