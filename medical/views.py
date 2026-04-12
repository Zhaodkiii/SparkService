import logging

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.http_cache import build_etag, normalize_etag
from common.response import error_response, success_response
from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    Medication,
    MedicationTakenRecord,
    MedExamDetail,
    MedicalCase,
    ModelChangeLog,
    Member,
    PrescriptionBatch,
    Surgery,
    Symptom,
    Visit,
)
from medical.serializers import (
    ExaminationReportSerializer,
    FollowUpSerializer,
    HealthExamReportSerializer,
    MedicationSerializer,
    MedicationTakenRecordSerializer,
    MedExamDetailSerializer,
    MedicalCaseSerializer,
    MemberSerializer,
    PrescriptionBatchSerializer,
    SurgerySerializer,
    SymptomSerializer,
    VisitSerializer,
)
from file_manager.models import ManagedFile
from file_manager.serializers import ManagedFileAttachmentOutSerializer

logger = logging.getLogger("medical.flow")


class WrappedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    etag_max_age = 120

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user, is_deleted=False)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        etag = self._build_collection_etag(queryset)
        if self._is_not_modified(request, etag):
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            return response

        serializer = self.get_serializer(queryset, many=True)
        response = success_response(serializer.data, msg="success", code=0, status_code=status.HTTP_200_OK)
        self._set_cache_headers(response, etag)
        return response

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        etag = self._build_object_etag(instance)
        if self._is_not_modified(request, etag):
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            return response

        serializer = self.get_serializer(instance)
        response = success_response(serializer.data, msg="success", code=0, status_code=status.HTTP_200_OK)
        self._set_cache_headers(response, etag)
        return response

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return success_response(serializer.data, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response({"id": instance.id}, msg="deleted", code=0, status_code=status.HTTP_200_OK)

    def _build_collection_etag(self, queryset):
        records = list(queryset.values_list("id", "updated_at"))
        payload = {
            "path": self.request.path,
            "query": self.request.query_params.dict(),
            "user_id": self.request.user.id,
            "records": records,
        }
        return build_etag(payload)

    def _build_object_etag(self, instance):
        payload = {"id": instance.id, "updated_at": instance.updated_at, "user_id": self.request.user.id}
        return build_etag(payload)

    def _is_not_modified(self, request, etag):
        incoming = normalize_etag(request.headers.get("If-None-Match"))
        if incoming == "":
            return False
        return incoming == normalize_etag(etag)

    def _set_cache_headers(self, response, etag):
        response["ETag"] = etag
        response["Cache-Control"] = f"private, max-age={self.etag_max_age}"


class MemberViewSet(WrappedModelViewSet):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer


class MedicalCaseViewSet(WrappedModelViewSet):
    queryset = MedicalCase.objects.select_related("member").all()
    serializer_class = MedicalCaseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset


class SymptomViewSet(WrappedModelViewSet):
    queryset = Symptom.objects.select_related("member", "medical_case").all()
    serializer_class = SymptomSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        return queryset


class VisitViewSet(WrappedModelViewSet):
    queryset = Visit.objects.select_related("member", "medical_case").all()
    serializer_class = VisitSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        return queryset


class SurgeryViewSet(WrappedModelViewSet):
    queryset = Surgery.objects.select_related("member", "medical_case").all()
    serializer_class = SurgerySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        return queryset


class FollowUpViewSet(WrappedModelViewSet):
    queryset = FollowUp.objects.select_related("member", "medical_case").all()
    serializer_class = FollowUpSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        return queryset


class ExaminationReportViewSet(WrappedModelViewSet):
    queryset = ExaminationReport.objects.select_related("member", "medical_record").all()
    serializer_class = ExaminationReportSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset


class HealthExamReportViewSet(WrappedModelViewSet):
    queryset = HealthExamReport.objects.select_related("member").all()
    serializer_class = HealthExamReportSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset


class MedExamDetailViewSet(WrappedModelViewSet):
    """明细表无 `user` 外键，通过 `member.user` 做数据隔离（勿复用 `WrappedModelViewSet.get_queryset` 的 user 过滤）。"""

    queryset = MedExamDetail.objects.select_related("member").all()
    serializer_class = MedExamDetailSerializer

    def get_queryset(self):
        queryset = MedExamDetail.objects.select_related("member").filter(
            member__user_id=self.request.user.id,
            is_deleted=False,
        )
        member_id = self.request.query_params.get("member_id")
        business_type = self.request.query_params.get("business_type")
        business_id = self.request.query_params.get("business_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if business_type:
            queryset = queryset.filter(business_type=business_type)
        if business_id:
            queryset = queryset.filter(business_id=business_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted", "updated_at"])


class PrescriptionBatchViewSet(WrappedModelViewSet):
    queryset = PrescriptionBatch.objects.select_related("member", "medical_case").all()
    serializer_class = PrescriptionBatchSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        return queryset


class MedicationViewSet(WrappedModelViewSet):
    queryset = Medication.objects.select_related("member", "batch").all()
    serializer_class = MedicationSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        batch_id = self.request.query_params.get("batch_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        return queryset


class MedicationTakenRecordViewSet(WrappedModelViewSet):
    queryset = MedicationTakenRecord.objects.select_related("member", "medication").all()
    serializer_class = MedicationTakenRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medication_id = self.request.query_params.get("medication_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medication_id:
            queryset = queryset.filter(medication_id=medication_id)
        return queryset


class MemberCompleteDataAPI(APIView):
    """成员医疗数据汇总（单接口）：病例汇总、症状/就诊/手术/随访、体检/检查报告头、处方批次与附件；不含检验/体检明细行。"""

    permission_classes = [IsAuthenticated]
    etag_max_age = 86400

    def get(self, request, member_id: int):
        try:
            member = Member.objects.get(id=member_id, user=request.user, is_deleted=False)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        medical_cases = (
            MedicalCase.objects.filter(user=request.user, is_deleted=False, member_id=member_id)
            .prefetch_related(
                "symptoms",
                Prefetch(
                    "prescription_batches",
                    queryset=PrescriptionBatch.objects.filter(is_deleted=False).prefetch_related("medications"),
                ),
            )
            .order_by("-created_at")
        )

        health_exam_reports = HealthExamReport.objects.filter(
            user=request.user,
            is_deleted=False,
            member_id=member_id,
        ).order_by("-exam_date", "-updated_at")

        examination_reports = ExaminationReport.objects.select_related("medical_record").filter(
            user=request.user,
            is_deleted=False,
            member_id=member_id,
        ).order_by("-performed_at", "-updated_at")

        prescription_batches = (
            PrescriptionBatch.objects.filter(user=request.user, is_deleted=False, member_id=member_id)
            .prefetch_related("medications")
            .order_by("-prescribed_at", "-updated_at")
        )

        symptoms = Symptom.objects.filter(user=request.user, is_deleted=False, member_id=member_id).order_by(
            "-created_at", "-updated_at", "-id"
        )
        visits = Visit.objects.filter(user=request.user, is_deleted=False, member_id=member_id).order_by(
            "-visited_at", "-updated_at", "-id"
        )
        surgeries = Surgery.objects.filter(user=request.user, is_deleted=False, member_id=member_id).order_by(
            "-performed_at", "-updated_at", "-id"
        )
        follow_ups = FollowUp.objects.filter(user=request.user, is_deleted=False, member_id=member_id).order_by(
            "-completed_at", "-updated_at", "-id"
        )

        standalone_medications = Medication.objects.none()

        etag = self._build_complete_etag(
            request=request,
            member=member,
            medical_cases=medical_cases,
            health_exam_reports=health_exam_reports,
            examination_reports=examination_reports,
            prescription_batches=prescription_batches,
            standalone_medications=standalone_medications,
            symptoms=symptoms,
            visits=visits,
            surgeries=surgeries,
            follow_ups=follow_ups,
        )
        if self._is_not_modified(request, etag):
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            self._set_cache_headers(response, etag)
            return response

        def attachments_payload(business_type: str, business_id: int):
            qs = ManagedFile.objects.filter(
                user=request.user,
                business_type=business_type,
                business_id=str(business_id),
                is_deleted=False,
            ).order_by("-created_at")
            return ManagedFileAttachmentOutSerializer(qs, many=True).data

        medical_cases_payload = []
        for c in medical_cases:
            symptom_names = [s.name for s in c.symptoms.all()]
            drug_names = []
            for pb in c.prescription_batches.all():
                for m in pb.medications.all():
                    dn = (m.drug_name or m.generic_name or "").strip()
                    if dn and dn not in drug_names:
                        drug_names.append(dn)
            medical_cases_payload.append(
                {
                    "id": c.id,
                    "member": c.member_id,
                    "record_type": c.record_type,
                    "status": c.status,
                    "title": c.title,
                    "hospital_name": c.hospital_name,
                    "age_at_visit": c.age_at_visit,
                    "diagnosis_summary": c.diagnosis_summary,
                    "extra": c.extra,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                    "symptoms": symptom_names,
                    "medications": drug_names,
                    "attachments": attachments_payload("medical_case", c.id),
                }
            )

        health_payload = []
        for h in health_exam_reports:
            row = dict(HealthExamReportSerializer(h).data)
            row.pop("raw_ocr", None)
            row["attachments"] = attachments_payload("health_exam_report", h.id)
            health_payload.append(row)

        exam_payload = []
        for e in examination_reports:
            row = dict(ExaminationReportSerializer(e).data)
            row.pop("raw_ocr", None)
            row["attachments"] = attachments_payload("examination_report", e.id)
            exam_payload.append(row)

        batch_payload = []
        for b in prescription_batches:
            row = dict(PrescriptionBatchSerializer(b).data)
            row["medications"] = MedicationSerializer(b.medications.all(), many=True).data
            row["attachments"] = attachments_payload("prescription_batch", b.id)
            batch_payload.append(row)

        standalone_payload = MedicationSerializer(standalone_medications, many=True).data

        symptoms_payload = SymptomSerializer(symptoms, many=True).data
        visits_payload = VisitSerializer(visits, many=True).data
        surgeries_payload = SurgerySerializer(surgeries, many=True).data
        follow_ups_payload = FollowUpSerializer(follow_ups, many=True).data

        payload = {
            "member_id": member_id,
            "member": MemberSerializer(member).data,
            "medical_cases": medical_cases_payload,
            "health_exam_reports": health_payload,
            "examination_reports": exam_payload,
            "prescription_batches": batch_payload,
            "standalone_medications": standalone_payload,
            "symptoms": symptoms_payload,
            "visits": visits_payload,
            "surgeries": surgeries_payload,
            "follow_ups": follow_ups_payload,
        }
        response = success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
        self._set_cache_headers(response, etag)
        return response

    def _build_complete_etag(
        self,
        request,
        member,
        medical_cases,
        health_exam_reports,
        examination_reports,
        prescription_batches,
        standalone_medications,
        symptoms,
        visits,
        surgeries,
        follow_ups,
    ):
        case_ids = [str(pk) for pk in medical_cases.values_list("id", flat=True)]
        hex_ids = [str(pk) for pk in health_exam_reports.values_list("id", flat=True)]
        er_ids = [str(pk) for pk in examination_reports.values_list("id", flat=True)]
        pb_ids = [str(pk) for pk in prescription_batches.values_list("id", flat=True)]

        att_q = []
        if case_ids:
            att_q.append(Q(business_type="medical_case", business_id__in=case_ids))
        if hex_ids:
            att_q.append(Q(business_type="health_exam_report", business_id__in=hex_ids))
        if er_ids:
            att_q.append(Q(business_type="examination_report", business_id__in=er_ids))
        if pb_ids:
            att_q.append(Q(business_type="prescription_batch", business_id__in=pb_ids))

        attachments_fingerprint = []
        if att_q:
            combined = att_q[0]
            for q in att_q[1:]:
                combined |= q
            attachments_fingerprint = list(
                ManagedFile.objects.filter(user=request.user, is_deleted=False)
                .filter(combined)
                .values_list("id", "updated_at")
            )

        payload = {
            "path": request.path,
            "user_id": request.user.id,
            "member": (member.id, member.updated_at),
            "collections": {
                "medical_cases": list(medical_cases.values_list("id", "updated_at")),
                "health_exam_reports": list(health_exam_reports.values_list("id", "updated_at")),
                "examination_reports": list(examination_reports.values_list("id", "updated_at")),
                "prescription_batches": list(prescription_batches.values_list("id", "updated_at")),
                "standalone_medications": list(standalone_medications.values_list("id", "updated_at")),
                "symptoms": list(symptoms.values_list("id", "updated_at")),
                "visits": list(visits.values_list("id", "updated_at")),
                "surgeries": list(surgeries.values_list("id", "updated_at")),
                "follow_ups": list(follow_ups.values_list("id", "updated_at")),
                "attachments": attachments_fingerprint,
            },
        }
        return build_etag(payload)

    def _is_not_modified(self, request, etag):
        incoming = normalize_etag(request.headers.get("If-None-Match"))
        if incoming == "":
            return False
        return incoming == normalize_etag(etag)

    def _set_cache_headers(self, response, etag):
        response["ETag"] = etag
        response["Cache-Control"] = f"private, max-age={self.etag_max_age}"


class _WorkflowBaseAPIView(APIView):
    permission_classes = [IsAuthenticated]
    _NULLISH_DATETIME_TOKENS = {"", "无", "未提及", "未知", "none", "null", "n/a", "na", "-", "--"}

    def _bind_files(self, user, business_type, business_id, file_ids):
        if not file_ids:
            return
        ManagedFile.objects.filter(user=user, id__in=file_ids, is_deleted=False).update(
            business_type=business_type,
            business_id=str(business_id),
        )

    def _validate_or_error(self, serializer):
        if serializer.is_valid():
            return None
        # 保留字段级结构，客户端可读化后统一拼接本地化前缀。
        return error_response(msg=serializer.errors, code=-1, status_code=status.HTTP_400_BAD_REQUEST)

    @classmethod
    def _normalize_nullable_datetime(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed.lower() in cls._NULLISH_DATETIME_TOKENS or trimmed in cls._NULLISH_DATETIME_TOKENS:
                return None
            return trimmed
        return value

    def _resolve_member_and_case(self, request, payload, default_case_title: str):
        member_id = payload.get("member")
        if not member_id:
            return None, None, error_response(
                msg={"member": [_("member is required")]},
                code=-1,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            member = Member.objects.get(id=member_id, user=request.user, is_deleted=False)
        except Member.DoesNotExist:
            return None, None, error_response(
                msg={"member": [_("invalid member")]},
                code=-1,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        medical_case_id = payload.get("medical_case")
        if medical_case_id:
            try:
                medical_case = MedicalCase.objects.get(
                    id=medical_case_id,
                    user=request.user,
                    is_deleted=False,
                )
            except MedicalCase.DoesNotExist:
                return None, None, error_response(
                    msg={"medical_case": [_("invalid medical_case")]},
                    code=-1,
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if medical_case.member_id != member.id:
                return None, None, error_response(
                    msg={"medical_case": [_("medical_case does not belong to member")]},
                    code=-1,
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            return member, medical_case, None

        # 兼容客户端传 medical_case = null：自动创建占位病例。
        medical_case = MedicalCase.objects.create(
            user=request.user,
            member=member,
            record_type="custom",
            status=MedicalCase.Status.DRAFT,
            title=default_case_title,
            diagnosis_summary="",
            extra={"source": "workflow_auto_case"},
        )
        return member, medical_case, None

    def _normalize_medication_payload(self, medication, batch, sort_order):
        """统一药品行字段（处方批次与用药工作流复用）；batch 为 ``PrescriptionBatch`` 实例。"""
        row = dict(medication)
        row["member"] = batch.member_id
        row["batch"] = batch.id
        row["sort_order"] = row.get("sort_order", sort_order)

        # Aera 风格字段兼容映射
        row["drug_name"] = row.get("drug_name") or row.get("name") or row.get("generic_name") or row.get("brand_name") or ""
        row["generic_name"] = row.get("generic_name") or row.get("name") or row["drug_name"]
        row["brand_name"] = row.get("brand_name", "")
        row["strength"] = row.get("strength") or row.get("specification") or ""
        row["dose_per_time"] = row.get("dose_per_time") or row.get("dosage") or ""
        row["frequency_text"] = row.get("frequency_text") or row.get("frequency") or ""
        row["instructions"] = row.get("instructions", "")
        row["period"] = row.get("period", "")
        row["route"] = row.get("route", "")
        row["dosage_form"] = row.get("dosage_form", "")
        row["dose_unit"] = row.get("dose_unit", "")
        row["frequency_code"] = row.get("frequency_code", "")
        row["reminder_enabled"] = row.get("reminder_enabled", False)
        row["reminder_times"] = row.get("reminder_times", [])

        if row.get("duration_days") in (None, ""):
            duration = row.get("duration")
            if isinstance(duration, int):
                row["duration_days"] = duration
            elif isinstance(duration, str):
                digits = "".join(ch for ch in duration if ch.isdigit())
                row["duration_days"] = int(digits) if digits else None

        return row


class MedicalCaseWorkflowSaveView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        serializer = MedicalCaseSerializer(data=payload)
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "medical_case", obj.id, file_ids)
        return success_response(serializer.data, msg="saved", code=0, status_code=status.HTTP_201_CREATED)


class HealthExamWorkflowSaveView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        detail_rows = payload.pop("details", [])
        serializer = HealthExamReportSerializer(data=payload)
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)

        created_details = []
        for idx, detail in enumerate(detail_rows):
            detail_payload = {
                "business_type": MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
                "business_id": obj.id,
                "member": obj.member_id,
                "category": detail.get("category", ""),
                "sub_category": detail.get("sub_category") or detail.get("subCategory", ""),
                "item_name": detail.get("item_name") or detail.get("itemName", ""),
                "item_code": detail.get("item_code") or detail.get("itemCode", ""),
                "result_value": detail.get("result_value") or detail.get("resultValue", ""),
                "unit": detail.get("unit", ""),
                "reference_range": detail.get("reference_range") or detail.get("referenceRange", ""),
                "flag": detail.get("flag", ""),
                "result_at": detail.get("result_at")
                or detail.get("resultAt")
                or (f"{obj.exam_date.isoformat()}T00:00:00Z" if obj.exam_date else None),
                "modality": detail.get("modality", ""),
                "body_part": detail.get("body_part") or detail.get("bodyPart", ""),
                "diagnosis": detail.get("diagnosis", ""),
                "extra": detail.get("extra", {}),
                "sort_order": detail.get("sort_order", detail.get("sortOrder", idx)),
            }
            detail_serializer = MedExamDetailSerializer(data=detail_payload)
            validation_error = self._validate_or_error(detail_serializer)
            if validation_error is not None:
                return validation_error
            created = detail_serializer.save()
            created_details.append(MedExamDetailSerializer(created).data)

        self._bind_files(request.user, "health_exam_report", obj.id, file_ids)
        return success_response(
            {"id": obj.id, "report": HealthExamReportSerializer(obj).data, "details": created_details},
            msg="saved",
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class MedicalReportWorkflowSaveView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        detail_rows = payload.pop("details", [])

        report_payload = {
            "user": request.user.id,
            "member": payload.get("member"),
            "medical_record": payload.get("medical_case"),
            "category": payload.get("category", "") or "medical_report",
            "sub_category": "",
            "item_name": payload.get("title", "") or "医疗报告",
            "performed_at": payload.get("date"),
            "reported_at": payload.get("date"),
            "organization_name": payload.get("organization_name") or payload.get("hospital", "") or "",
            "department_name": "",
            "doctor_name": payload.get("doctor_name") or payload.get("doctor", "") or "",
            "findings": payload.get("content", "") or "",
            "impression": payload.get("content", "") or "",
            "source": ExaminationReport.Source.OCR,
            "raw_ocr": {"text": payload.get("content", "") or ""},
            "status": ExaminationReport.Status.DRAFT,
            "extra": {"source": "typed_upload"},
        }
        report_serializer = ExaminationReportSerializer(data=report_payload)
        validation_error = self._validate_or_error(report_serializer)
        if validation_error is not None:
            return validation_error
        report = report_serializer.save(user=request.user)

        created_details = []
        for idx, detail in enumerate(detail_rows):
            detail_payload = {
                "business_type": MedExamDetail.BusinessType.EXAMINATION_REPORT,
                "business_id": report.id,
                "member": report.member_id,
                "category": detail.get("category", "") or report.category,
                "sub_category": detail.get("sub_category", ""),
                "item_name": detail.get("item_name", "") or report.item_name,
                "item_code": detail.get("item_code", ""),
                "result_value": detail.get("result_value", ""),
                "unit": detail.get("unit", ""),
                "reference_range": detail.get("reference_range", ""),
                "flag": detail.get("flag", ""),
                "result_at": detail.get("result_at", report.reported_at),
                "modality": detail.get("modality", ""),
                "body_part": detail.get("body_part", ""),
                "diagnosis": detail.get("diagnosis", ""),
                "extra": detail.get("extra", {}),
                "sort_order": detail.get("sort_order", idx),
            }
            detail_serializer = MedExamDetailSerializer(data=detail_payload)
            validation_error = self._validate_or_error(detail_serializer)
            if validation_error is not None:
                return validation_error
            created = detail_serializer.save()
            created_details.append(MedExamDetailSerializer(created).data)

        self._bind_files(request.user, "examination_report", report.id, file_ids)
        return success_response(
            {"id": report.id, "report": ExaminationReportSerializer(report).data, "details": created_details},
            msg="saved",
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class PrescriptionWorkflowSaveView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        medications = payload.pop("medications", [])
        serializer = PrescriptionBatchSerializer(data=payload)
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        batch = serializer.save(user=request.user)

        medication_results = []
        for idx, medication in enumerate(medications):
            row = self._normalize_medication_payload(medication, batch, idx)
            item_serializer = MedicationSerializer(data=row)
            validation_error = self._validate_or_error(item_serializer)
            if validation_error is not None:
                return validation_error
            item = item_serializer.save(user=request.user)
            medication_results.append(MedicationSerializer(item).data)

        self._bind_files(request.user, "prescription_batch", batch.id, file_ids)
        return success_response(
            {"batch": PrescriptionBatchSerializer(batch).data, "medications": medication_results},
            msg="saved",
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class MedicationWorkflowSaveView(_WorkflowBaseAPIView):
    """用药工作流保存。

    - **单条（兼容）**：请求体为单条 ``Medication`` 字段（须含 ``member``、``batch``）。
    - **批量**：请求体含 ``medications`` 为非空数组时，先为 **首条或顶层** 指定的 ``member``
      创建占位 ``PrescriptionBatch``，再逐条写入药品行；**成员 ID 以第一条药品上的 ``member`` 为准**，
      若首条未带则使用顶层 ``member``。各行的 ``member`` 将统一覆盖为该值，避免串档。
    """

    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        medications = payload.pop("medications", None)

        if medications is not None:
            if not isinstance(medications, list) or len(medications) == 0:
                return error_response(
                    msg={"medications": [_("medications must be a non-empty array")]},
                    code=-1,
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            first = medications[0]
            primary_member = None
            if isinstance(first, dict):
                primary_member = first.get("member")
            if primary_member is None:
                primary_member = payload.get("member")
            if primary_member is None:
                return error_response(
                    msg={"member": [_("set member on first medication row or as top-level member")]},
                    code=-1,
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if not Member.objects.filter(id=primary_member, user=request.user, is_deleted=False).exists():
                return error_response(
                    msg={"member": [_("invalid member")]},
                    code=-1,
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            batch_payload = {
                "member": primary_member,
                "diagnosis": "",
                "prescriber_name": "",
                "institution_name": "",
                "extra": {"source": "medication_workflow_bulk"},
            }
            batch_serializer = PrescriptionBatchSerializer(data=batch_payload)
            validation_error = self._validate_or_error(batch_serializer)
            if validation_error is not None:
                return validation_error
            batch = batch_serializer.save(user=request.user)

            medication_results = []
            for idx, med in enumerate(medications):
                if not isinstance(med, dict):
                    return error_response(
                        msg={"medications": [_("each item must be an object")]},
                        code=-1,
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
                med = {**med, "member": primary_member}
                row = self._normalize_medication_payload(med, batch, idx)
                row["member"] = primary_member
                item_serializer = MedicationSerializer(data=row)
                validation_error = self._validate_or_error(item_serializer)
                if validation_error is not None:
                    return validation_error
                item = item_serializer.save(user=request.user)
                medication_results.append(MedicationSerializer(item).data)

            self._bind_files(request.user, "prescription_batch", batch.id, file_ids)
            first_id = medication_results[0]["id"] if medication_results else batch.id
            return success_response(
                {
                    "id": first_id,
                    "batch": PrescriptionBatchSerializer(batch).data,
                    "medications": medication_results,
                },
                msg="saved",
                code=0,
                status_code=status.HTTP_201_CREATED,
            )

        serializer = MedicationSerializer(data=payload)
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "medication", obj.id, file_ids)
        return success_response(serializer.data, msg="saved", code=0, status_code=status.HTTP_201_CREATED)


class SymptomWorkflowCreateView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        member, medical_case, resolve_error = self._resolve_member_and_case(request, payload, default_case_title="症状记录")
        if resolve_error is not None:
            return resolve_error

        symptom_payload = {
            "member": member.id,
            "medical_case": medical_case.id,
            "name": payload.get("name"),
            "code": payload.get("code", ""),
            "severity": payload.get("severity", ""),
            "started_at": self._normalize_nullable_datetime(payload.get("started_at")),
            "duration_value": payload.get("duration_value"),
            "duration_unit": payload.get("duration_unit", ""),
            "body_part": payload.get("body_part", ""),
            "notes": payload.get("notes", ""),
            "extra": payload.get("extra", {}),
        }
        serializer = SymptomSerializer(data=symptom_payload, context={"request": request})
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "symptom", obj.id, file_ids)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class VisitWorkflowCreateView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        member, medical_case, resolve_error = self._resolve_member_and_case(request, payload, default_case_title="就诊记录")
        if resolve_error is not None:
            return resolve_error

        visit_payload = {
            "member": member.id,
            "medical_case": medical_case.id,
            "visit_type": payload.get("visit_type", "") or "custom",
            "visited_at": self._normalize_nullable_datetime(payload.get("visited_at")),
            "department": payload.get("department", ""),
            "doctor_name": payload.get("doctor_name", ""),
            "visit_no": payload.get("visit_no", ""),
            "notes": payload.get("notes", ""),
            "extra": payload.get("extra", {}),
        }
        serializer = VisitSerializer(data=visit_payload, context={"request": request})
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "visit", obj.id, file_ids)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class SurgeryWorkflowCreateView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        member, medical_case, resolve_error = self._resolve_member_and_case(request, payload, default_case_title="手术记录")
        if resolve_error is not None:
            return resolve_error

        surgery_payload = {
            "member": member.id,
            "medical_case": medical_case.id,
            "procedure_name": payload.get("procedure_name"),
            "procedure_code": payload.get("procedure_code", ""),
            "site": payload.get("site", ""),
            "performed_at": self._normalize_nullable_datetime(payload.get("performed_at")),
            "surgeon": payload.get("surgeon", ""),
            "anesthesia_type": payload.get("anesthesia_type", ""),
            "incision_level": payload.get("incision_level", ""),
            "asa_class": payload.get("asa_class", ""),
            "notes": payload.get("notes", ""),
            "extra": payload.get("extra", {}),
        }
        serializer = SurgerySerializer(data=surgery_payload, context={"request": request})
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "surgery", obj.id, file_ids)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class FollowUpWorkflowCreateView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        member, medical_case, resolve_error = self._resolve_member_and_case(request, payload, default_case_title="随访记录")
        if resolve_error is not None:
            return resolve_error

        follow_up_payload = {
            "member": member.id,
            "medical_case": medical_case.id,
            "planned_at": self._normalize_nullable_datetime(payload.get("planned_at")),
            "completed_at": self._normalize_nullable_datetime(payload.get("completed_at")),
            "status": payload.get("status", "") or "initial",
            "method": payload.get("method", ""),
            "outcome": payload.get("outcome", ""),
            "next_action": payload.get("next_action", ""),
            "extra": payload.get("extra", {}),
        }
        serializer = FollowUpSerializer(data=follow_up_payload, context={"request": request})
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "follow_up", obj.id, file_ids)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class MedicalAttachmentBatchBindView(_WorkflowBaseAPIView):
    @transaction.atomic
    def patch(self, request):
        items = request.data.get("items", [])
        updated = 0
        for item in items:
            file_id = item.get("file_id")
            business_type = item.get("business_type")
            business_id = item.get("business_id")
            if not file_id or not business_type or business_id is None:
                continue
            count = ManagedFile.objects.filter(user=request.user, id=file_id, is_deleted=False).update(
                business_type=business_type,
                business_id=str(business_id),
            )
            updated += count
        return success_response({"updated": updated}, msg="updated", code=0, status_code=status.HTTP_200_OK)


class CombinedMedicalCreateAPIView(APIView):
    """
    一次性创建完整医疗记录（组合创建 API）。

    流程：
    1) member: 若带 id → 校验存在与归属；否则创建；得到 member_id
    2) medical_case: 必传，使用 member_id 创建；得到 case_id
    3) symptom/visit/surgery/follow-up/examination_reports/prescription_batches: 可选，有则使用 case_id 逐一创建
    4) 返回统一结果（已创建对象的精简信息/主键）

    参考：HealthClient 的 SeverMedicalCreateAPI 和 ZhaodkDream 的 SeverMedicalCreateAPI
    """
    permission_classes = [IsAuthenticated]
    _NULLISH_DATETIME_TOKENS = {"", "无", "未提及", "未知", "none", "null", "n/a", "na", "-", "--"}

    @classmethod
    def _normalize_nullable_datetime(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed.lower() in cls._NULLISH_DATETIME_TOKENS or trimmed in cls._NULLISH_DATETIME_TOKENS:
                return None
            return trimmed
        return value

    @transaction.atomic
    def post(self, request):
        data = request.data or {}

        # ------ (0) 基本校验：member + medical_case 必须提供 ------
        member_payload = data.get("member")
        case_payload = data.get("medical_case")

        if not member_payload or not case_payload:
            return Response(
                {"detail": "member 与 medical_case 均为必填"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # =========================================================
        # (1) 处理成员：若带 id → 校验并取用；否则创建
        # =========================================================
        member_id = member_payload.get("id")
        if member_id:
            # 有 id：校验成员存在 & 归属权限
            try:
                member_obj = Member.objects.get(pk=member_id, is_deleted=False)
            except Member.DoesNotExist:
                return Response(
                    {"detail": f"成员(id={member_id})不存在"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if (not request.user.is_staff) and (member_obj.user_id != request.user.id):
                return Response({"detail": "无权使用该成员"}, status=status.HTTP_403_FORBIDDEN)
        else:
            # 无 id：创建成员
            ser_m = MemberSerializer(data=member_payload, context={"request": request})
            ser_m.is_valid(raise_exception=True)
            # user 在 Serializer 中为 read_only，须通过 save(user=…) 写入（见 DRF ModelSerializer.save）
            member_obj = ser_m.save(user=request.user)

        member_id = member_obj.id

        # =========================================================
        # (2) 处理病历 MedicalCase：必须
        # =========================================================
        case_payload["member"] = member_id
        case_ser = MedicalCaseSerializer(data=case_payload, context={"request": request})
        case_ser.is_valid(raise_exception=True)
        case_obj = case_ser.save(user=request.user)
        case_id = case_obj.id

        # =========================================================
        # (3) 可选创建：symptom/visit/surgery/follow-up/examination_reports/prescription_batches
        # =========================================================
        result = {
            "member_id": member_id,
            "medical_case_id": case_id,
            "created_at": timezone.now().isoformat(),
        }

        # ---------- symptom（单个，可选）----------
        symptom_payload = data.get("symptom")
        if symptom_payload:
            payload = dict(symptom_payload)
            payload["started_at"] = self._normalize_nullable_datetime(payload.get("started_at"))
            payload["member"] = member_id
            payload["medical_case"] = case_id
            ser = SymptomSerializer(data=payload, context={"request": request})
            ser.is_valid(raise_exception=True)
            obj = ser.save(user=request.user)
            result["symptom_id"] = obj.id

        # ---------- visit（单个，可选）----------
        visit_payload = data.get("visit")
        if visit_payload:
            payload = dict(visit_payload)
            payload["visited_at"] = self._normalize_nullable_datetime(payload.get("visited_at"))
            payload["member"] = member_id
            payload["medical_case"] = case_id
            ser = VisitSerializer(data=payload, context={"request": request})
            ser.is_valid(raise_exception=True)
            obj = ser.save(user=request.user)
            result["visit_id"] = obj.id

        # ---------- surgery（单个，可选）----------
        surgery_payload = data.get("surgery")
        if surgery_payload:
            payload = dict(surgery_payload)
            payload["performed_at"] = self._normalize_nullable_datetime(payload.get("performed_at"))
            payload["member"] = member_id
            payload["medical_case"] = case_id
            ser = SurgerySerializer(data=payload, context={"request": request})
            ser.is_valid(raise_exception=True)
            obj = ser.save(user=request.user)
            result["surgery_id"] = obj.id

        # ---------- follow_up（单个，可选）----------
        follow_up_payload = data.get("follow_up")
        if follow_up_payload:
            payload = dict(follow_up_payload)
            payload["planned_at"] = self._normalize_nullable_datetime(payload.get("planned_at"))
            payload["completed_at"] = self._normalize_nullable_datetime(payload.get("completed_at"))
            payload["member"] = member_id
            payload["medical_case"] = case_id
            ser = FollowUpSerializer(data=payload, context={"request": request})
            ser.is_valid(raise_exception=True)
            obj = ser.save(user=request.user)
            result["follow_up_id"] = obj.id

        # ---------- examination_reports（批量，可选）----------
        exam_reports_payload = data.get("examination_reports") or []
        if isinstance(exam_reports_payload, list) and exam_reports_payload:
            result["examination_report_ids"] = []
            for rep in exam_reports_payload:
                payload = dict(rep or {})
                payload["performed_at"] = self._normalize_nullable_datetime(payload.get("performed_at"))
                payload["reported_at"] = self._normalize_nullable_datetime(payload.get("reported_at"))
                payload["member"] = member_id
                # ExaminationReport 模型使用 medical_record 字段名（不是 medical_case）
                payload["medical_record"] = case_id
                # details 单独处理
                details = payload.pop("details", [])

                ser = ExaminationReportSerializer(data=payload, context={"request": request})
                ser.is_valid(raise_exception=True)
                obj = ser.save(user=request.user)
                result["examination_report_ids"].append(obj.id)

                # 创建明细
                for idx, detail in enumerate(details):
                    normalized_detail = dict(detail or {})
                    normalized_detail["result_at"] = self._normalize_nullable_datetime(normalized_detail.get("result_at"))
                    detail_payload = {
                        "business_type": MedExamDetail.BusinessType.EXAMINATION_REPORT,
                        "business_id": obj.id,
                        "member": member_id,
                        **normalized_detail,
                    }
                    detail_ser = MedExamDetailSerializer(data=detail_payload, context={"request": request})
                    detail_ser.is_valid(raise_exception=True)
                    detail_ser.save()

        # ---------- prescription_batches（批量，可选）----------
        batches_payload = data.get("prescription_batches") or []
        if isinstance(batches_payload, list) and batches_payload:
            result["prescription_batch_ids"] = []
            for batch_data in batches_payload:
                batch_payload = dict(batch_data or {})
                batch_payload["member"] = member_id
                batch_payload["medical_case"] = case_id
                # medications 单独处理
                medications = batch_payload.pop("medications", [])

                batch_ser = PrescriptionBatchSerializer(data=batch_payload, context={"request": request})
                batch_ser.is_valid(raise_exception=True)
                batch_obj = batch_ser.save(user=request.user)
                batch_id = batch_obj.id
                result["prescription_batch_ids"].append(batch_id)

                # 创建该批次下的用药记录
                for idx, med in enumerate(medications):
                    med_payload = dict(med or {})
                    med_payload["member"] = member_id
                    med_payload["batch"] = batch_id
                    med_ser = MedicationSerializer(data=med_payload, context={"request": request})
                    med_ser.is_valid(raise_exception=True)
                    med_ser.save(user=request.user)

        # ---------- source_file_ids（附件绑定，可选）----------
        source_file_ids = data.get("source_file_ids") or []
        if isinstance(source_file_ids, list) and source_file_ids:
            # 绑定文件到病历
            for file_id in source_file_ids:
                try:
                    file_record = ManagedFile.objects.get(id=file_id, user=request.user)
                    file_record.business_type = "medical_case"
                    file_record.business_id = str(case_id)
                    file_record.save(update_fields=["business_type", "business_id"])
                except ManagedFile.DoesNotExist:
                    pass  # 忽略不存在的文件

        return Response(result, status=status.HTTP_201_CREATED)
