import logging

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.http_cache import build_etag, normalize_etag
from common.response import error_response, success_response
from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    HealthMetricRecord,
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
    HealthMetricRecordSerializer,
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


class HealthMetricRecordViewSet(WrappedModelViewSet):
    queryset = HealthMetricRecord.objects.all()
    serializer_class = HealthMetricRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        profile_uid = self.request.query_params.get("profile_client_uid")
        if profile_uid:
            queryset = queryset.filter(profile_client_uid=profile_uid)
        return queryset


class MemberMedicalSummaryView(APIView):
    permission_classes = [IsAuthenticated]
    etag_max_age = 120

    def get(self, request, member_id: int):
        try:
            member = Member.objects.get(id=member_id, user=request.user, is_deleted=False)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        medical_cases = MedicalCase.objects.select_related("member").filter(
            user=request.user,
            is_deleted=False,
            member_id=member_id,
        )
        health_exam_reports = HealthExamReport.objects.select_related("member").filter(
            user=request.user,
            is_deleted=False,
            member_id=member_id,
        )
        examination_reports = ExaminationReport.objects.select_related("member", "medical_record").filter(
            user=request.user,
            is_deleted=False,
            member_id=member_id,
        )
        medications = Medication.objects.select_related("member", "batch").filter(
            user=request.user,
            is_deleted=False,
            member_id=member_id,
        )
        medication_taken_records = MedicationTakenRecord.objects.select_related("member", "medication").filter(
            user=request.user,
            is_deleted=False,
            member_id=member_id,
        )

        etag = self._build_summary_etag(
            request=request,
            member=member,
            medical_cases=medical_cases,
            health_exam_reports=health_exam_reports,
            examination_reports=examination_reports,
            medications=medications,
            medication_taken_records=medication_taken_records,
        )
        if self._is_not_modified(request, etag):
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            self._set_cache_headers(response, etag)
            return response

        payload = {
            "member": MemberSerializer(member).data,
            "medical_cases": MedicalCaseSerializer(medical_cases, many=True).data,
            "health_exam_reports": HealthExamReportSerializer(health_exam_reports, many=True).data,
            "examination_reports": ExaminationReportSerializer(examination_reports, many=True).data,
            "medications": MedicationSerializer(medications, many=True).data,
            "medication_taken_records": MedicationTakenRecordSerializer(medication_taken_records, many=True).data,
        }
        response = success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
        self._set_cache_headers(response, etag)
        return response

    def _build_summary_etag(
        self,
        request,
        member,
        medical_cases,
        health_exam_reports,
        examination_reports,
        medications,
        medication_taken_records,
    ):
        payload = {
            "path": request.path,
            "user_id": request.user.id,
            "member": (member.id, member.updated_at),
            "collections": {
                "medical_cases": list(medical_cases.values_list("id", "updated_at")),
                "health_exam_reports": list(health_exam_reports.values_list("id", "updated_at")),
                "examination_reports": list(examination_reports.values_list("id", "updated_at")),
                "medications": list(medications.values_list("id", "updated_at")),
                "medication_taken_records": list(medication_taken_records.values_list("id", "updated_at")),
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
            "member": payload.get("member"),
            "medical_record": payload.get("medical_case"),
            "category": payload.get("report_type", "") or "medical_report",
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

    def _normalize_medication_payload(self, medication, batch, sort_order):
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


class MedicationWorkflowSaveView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        serializer = MedicationSerializer(data=payload)
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "medication", obj.id, file_ids)
        return success_response(serializer.data, msg="saved", code=0, status_code=status.HTTP_201_CREATED)


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
