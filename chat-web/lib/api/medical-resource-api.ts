import type { SparkHttpClient } from "@/lib/api/http-client";
import type { HealthResourceReference, MedicalExamDetail, MedicalResourceRecord } from "@/types/medical-resource";

function segment(value: string | number): string {
  return encodeURIComponent(String(value));
}

const resourceKinds: Record<string, string> = {
  medical_case: "cases",
  health_exam_report: "health-exam-reports",
  examination_report: "examination-reports",
  medication_plan: "medication-plans",
  medicine_box: "medicine-boxes",
  "medicine-box": "medicine-boxes",
  member_key_indicator: "member-key-indicators",
};

export class SparkMedicalResourceApi {
  constructor(private readonly http: SparkHttpClient) {}

  getResource(reference: HealthResourceReference): Promise<MedicalResourceRecord> {
    const kind = resourceKinds[reference.resourceType];
    if (!kind) return Promise.reject(new Error("暂不支持该健康资料类型"));
    return this.http.requestOrThrow<MedicalResourceRecord>("GET", `/api/v1/medical/resources/${segment(reference.resourceId)}/?kind=${segment(kind)}&member_id=${segment(reference.memberId)}`);
  }

  async getExamDetails(reference: HealthResourceReference): Promise<MedicalExamDetail[]> {
    if (reference.resourceType !== "examination_report" && reference.resourceType !== "health_exam_report") return [];
    const businessType = reference.resourceType;
    const data = await this.http.requestOrThrow<MedicalExamDetail[] | { items?: MedicalExamDetail[] }>(
      "GET",
      `/api/v1/medical/resources/?kind=med-exam-details&member_id=${segment(reference.memberId)}&business_type=${segment(businessType)}&business_id=${segment(reference.resourceId)}`,
    );
    return Array.isArray(data) ? data : data.items ?? [];
  }
}
