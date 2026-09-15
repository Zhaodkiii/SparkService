export type HealthResourceType =
  | "medical_case"
  | "health_exam_report"
  | "examination_report"
  | "medication_plan"
  | "medicine_box"
  | "member_key_indicator";

export interface HealthResourceReference {
  resourceType: string;
  resourceId: number;
  memberId: number;
  refIndex?: number;
}

export interface MedicalResourceAttachment {
  id?: number | string;
  original_name?: string;
  filename?: string;
  mime_type?: string;
  file_size?: number;
  file_url?: string;
  download_url?: string;
  url?: string;
}

export interface MedicalExamDetail {
  id: number;
  business_type?: string;
  business_id?: number;
  member?: number;
  category?: string;
  sub_category?: string;
  item_name?: string;
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
  sort_order?: number;
  updated_at?: string;
}

export type MedicalResourceRecord = Record<string, unknown> & {
  id?: number;
  attachments?: MedicalResourceAttachment[];
};
