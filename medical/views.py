import logging

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.http_cache import build_etag, normalize_etag
from common.response import success_response
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
    MedicalReport,
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
    MedicalReportSerializer,
    MedicalSnapshotUploadSerializer,
    MemberSerializer,
    PrescriptionBatchSerializer,
    SurgerySerializer,
    SymptomSerializer,
    VisitSerializer,
)

logger = logging.getLogger(__name__)


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
    queryset = MedExamDetail.objects.select_related("member").all()
    serializer_class = MedExamDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
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


class MedicalReportViewSet(WrappedModelViewSet):
    queryset = MedicalReport.objects.select_related("member", "medical_case").all()
    serializer_class = MedicalReportSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset


class PrescriptionBatchViewSet(WrappedModelViewSet):
    queryset = PrescriptionBatch.objects.select_related("member", "medical_case").all()
    serializer_class = PrescriptionBatchSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
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


class MedicalSyncBootstrapView(APIView):
    permission_classes = [IsAuthenticated]
    etag_max_age = 120

    def get(self, request):
        members = list(Member.objects.filter(user=request.user, is_deleted=False).values())
        medical_cases = list(MedicalCase.objects.filter(user=request.user, is_deleted=False).values())
        symptoms = list(Symptom.objects.filter(user=request.user, is_deleted=False).values())
        visits = list(Visit.objects.filter(user=request.user, is_deleted=False).values())
        surgeries = list(Surgery.objects.filter(user=request.user, is_deleted=False).values())
        follow_ups = list(FollowUp.objects.filter(user=request.user, is_deleted=False).values())
        health_exam_reports = list(HealthExamReport.objects.filter(user=request.user, is_deleted=False).values())
        examination_reports = list(ExaminationReport.objects.filter(user=request.user, is_deleted=False).values())
        med_exam_details = list(MedExamDetail.objects.filter(is_deleted=False, member__user=request.user).values())
        medical_reports = list(MedicalReport.objects.filter(user=request.user, is_deleted=False).values())
        prescription_batches = list(PrescriptionBatch.objects.filter(user=request.user, is_deleted=False).values())
        medications = list(Medication.objects.filter(user=request.user, is_deleted=False).values())
        medication_taken_records = list(MedicationTakenRecord.objects.filter(user=request.user, is_deleted=False).values())
        health_metrics = list(HealthMetricRecord.objects.filter(user=request.user, is_deleted=False).values())

        payload = {
            "members": members,
            "medical_cases": medical_cases,
            "symptoms": symptoms,
            "visits": visits,
            "surgeries": surgeries,
            "follow_ups": follow_ups,
            "health_exam_reports": health_exam_reports,
            "examination_reports": examination_reports,
            "med_exam_details": med_exam_details,
            "medical_reports": medical_reports,
            "prescription_batches": prescription_batches,
            "medications": medications,
            "medication_taken_records": medication_taken_records,
            "health_metrics": health_metrics,
        }
        etag = build_etag({"user_id": request.user.id, "signature": self._snapshot_signature(request.user.id)})
        incoming = normalize_etag(request.headers.get("If-None-Match"))
        if incoming and incoming == normalize_etag(etag):
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            return response

        response = success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
        response["ETag"] = etag
        # response["Cache-Control"] = f"private, max-age={self.etag_max_age}"
        return response

    def _snapshot_signature(self, user_id):
        def signature_for(model):
            if model is MedExamDetail:
                rows = model.objects.filter(member__user_id=user_id, is_deleted=False).values_list("id", "updated_at")
            else:
                rows = model.objects.filter(user_id=user_id, is_deleted=False).values_list("id", "updated_at")
            count = 0
            latest = ""
            id_sum = 0
            for row_id, updated_at in rows:
                count += 1
                id_sum += int(row_id)
                if updated_at:
                    stamp = updated_at.isoformat()
                    if stamp > latest:
                        latest = stamp
            return {"count": count, "latest": latest, "id_sum": id_sum}

        return {
            "members": signature_for(Member),
            "medical_cases": signature_for(MedicalCase),
            "symptoms": signature_for(Symptom),
            "visits": signature_for(Visit),
            "surgeries": signature_for(Surgery),
            "follow_ups": signature_for(FollowUp),
            "health_exam_reports": signature_for(HealthExamReport),
            "examination_reports": signature_for(ExaminationReport),
            "med_exam_details": signature_for(MedExamDetail),
            "medical_reports": signature_for(MedicalReport),
            "prescription_batches": signature_for(PrescriptionBatch),
            "medications": signature_for(Medication),
            "medication_taken_records": signature_for(MedicationTakenRecord),
            "health_metrics": signature_for(HealthMetricRecord),
        }


class MedicalSyncUploadView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = MedicalSnapshotUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        self._upsert_members(request.user.id, payload.get("members", []))
        self._upsert_medical_cases(request.user.id, payload.get("medical_cases", []))
        self._upsert_symptoms(request.user.id, payload.get("symptoms", []))
        self._upsert_visits(request.user.id, payload.get("visits", []))
        self._upsert_surgeries(request.user.id, payload.get("surgeries", []))
        self._upsert_follow_ups(request.user.id, payload.get("follow_ups", []))
        self._upsert_health_exam_reports(request.user.id, payload.get("health_exam_reports", []))
        self._upsert_examination_reports(request.user.id, payload.get("examination_reports", []))
        self._upsert_med_exam_details(request.user.id, payload.get("med_exam_details", []))
        self._upsert_medical_reports(request.user.id, payload.get("medical_reports", []))
        self._upsert_prescription_batches(request.user.id, payload.get("prescription_batches", []))
        self._upsert_medications(request.user.id, payload.get("medications", []))
        self._upsert_medication_taken_records(request.user.id, payload.get("medication_taken_records", []))
        self._upsert_health_metrics(request.user.id, payload.get("health_metrics", []))

        return success_response({"uploaded": True}, msg="uploaded", code=0, status_code=status.HTTP_200_OK)

    def _upsert_members(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                Member.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            Member.objects.create(**defaults)
        logger.info("medical.sync.members.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_medical_cases(self, user_id, rows):
        allowed_fields = {
            "member_id",
            "record_type",
            "status",
            "title",
            "hospital_name",
            "age_at_visit",
            "diagnosis_summary",
            "extra",
        }
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            if member_id:
                row["member_id"] = member_id
            if not row.get("member_id"):
                continue
            safe_row = {key: value for key, value in row.items() if key in allowed_fields}
            defaults = {**safe_row, "user_id": user_id, "is_deleted": False}
            if row_id:
                MedicalCase.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            MedicalCase.objects.create(**defaults)
        logger.info("medical.sync.medical_cases.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _resolve_case_for_row(self, user_id, member_id, medical_case_id, entity_name):
        """校验子表 user/member 与主档一致，避免跨成员错误挂载。"""
        if not member_id or not medical_case_id:
            logger.warning(
                f"medical.sync.{entity_name}.skipped_missing_relation",
                extra={"user_id": user_id, "member_id": member_id, "medical_case_id": medical_case_id},
            )
            return None
        medical_case = MedicalCase.objects.filter(id=medical_case_id, user_id=user_id, is_deleted=False).first()
        if not medical_case:
            logger.warning(
                f"medical.sync.{entity_name}.skipped_case_not_found",
                extra={"user_id": user_id, "member_id": member_id, "medical_case_id": medical_case_id},
            )
            return None
        if medical_case.member_id != int(member_id):
            logger.warning(
                f"medical.sync.{entity_name}.skipped_member_mismatch",
                extra={
                    "user_id": user_id,
                    "member_id": member_id,
                    "medical_case_id": medical_case_id,
                    "case_member_id": medical_case.member_id,
                },
            )
            return None
        return medical_case

    def _upsert_symptoms(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            medical_case_id = row.pop("medical_case", None) or row.pop("medical_case_id", None)
            if not self._resolve_case_for_row(user_id, member_id, medical_case_id, "symptoms"):
                continue
            row["member_id"] = member_id
            row["medical_case_id"] = medical_case_id
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                Symptom.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            Symptom.objects.create(**defaults)
        logger.info("medical.sync.symptoms.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_visits(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            medical_case_id = row.pop("medical_case", None) or row.pop("medical_case_id", None)
            if not self._resolve_case_for_row(user_id, member_id, medical_case_id, "visits"):
                continue
            row["member_id"] = member_id
            row["medical_case_id"] = medical_case_id
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                Visit.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            Visit.objects.create(**defaults)
        logger.info("medical.sync.visits.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_surgeries(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            medical_case_id = row.pop("medical_case", None) or row.pop("medical_case_id", None)
            if not self._resolve_case_for_row(user_id, member_id, medical_case_id, "surgeries"):
                continue
            row["member_id"] = member_id
            row["medical_case_id"] = medical_case_id
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                Surgery.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            Surgery.objects.create(**defaults)
        logger.info("medical.sync.surgeries.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_follow_ups(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            medical_case_id = row.pop("medical_case", None) or row.pop("medical_case_id", None)
            if not self._resolve_case_for_row(user_id, member_id, medical_case_id, "follow_ups"):
                continue
            row["member_id"] = member_id
            row["medical_case_id"] = medical_case_id
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                FollowUp.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            FollowUp.objects.create(**defaults)
        logger.info("medical.sync.follow_ups.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_health_exam_reports(self, user_id, rows):
        allowed_fields = {
            "institution_name",
            "report_no",
            "exam_date",
            "exam_type",
            "summary",
            "source",
            "raw_ocr",
            "status",
            "extra",
        }
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            if member_id:
                row["member_id"] = member_id
            if not row.get("member_id"):
                continue
            safe_row = {key: value for key, value in row.items() if key in allowed_fields or key == "member_id"}
            defaults = {**safe_row, "user_id": user_id, "is_deleted": False}
            if row_id:
                HealthExamReport.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            HealthExamReport.objects.create(**defaults)
        logger.info("medical.sync.health_exam_reports.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_examination_reports(self, user_id, rows):
        allowed_fields = {
            "category",
            "sub_category",
            "item_name",
            "performed_at",
            "reported_at",
            "organization_name",
            "department_name",
            "doctor_name",
            "findings",
            "impression",
            "source",
            "raw_ocr",
            "status",
            "extra",
        }
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            medical_record_id = row.pop("medical_record", None) or row.pop("medical_record_id", None)
            if member_id:
                row["member_id"] = member_id
            if medical_record_id:
                row["medical_record_id"] = medical_record_id
            if not row.get("member_id"):
                continue
            safe_row = {key: value for key, value in row.items() if key in allowed_fields or key in {"member_id", "medical_record_id"}}
            defaults = {**safe_row, "user_id": user_id, "is_deleted": False}
            if row_id:
                ExaminationReport.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            ExaminationReport.objects.create(**defaults)
        logger.info("medical.sync.examination_reports.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_med_exam_details(self, user_id, rows):
        allowed_fields = {
            "business_type",
            "business_id",
            "category",
            "sub_category",
            "item_name",
            "item_code",
            "result_value",
            "unit",
            "reference_range",
            "flag",
            "result_at",
            "modality",
            "body_part",
            "diagnosis",
            "extra",
            "sort_order",
        }
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            if member_id:
                row["member_id"] = member_id
            if not row.get("member_id"):
                continue
            if row.get("business_type") not in {
                MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
                MedExamDetail.BusinessType.EXAMINATION_REPORT,
            }:
                continue
            safe_row = {key: value for key, value in row.items() if key in allowed_fields or key == "member_id"}
            defaults = {**safe_row, "is_deleted": False}
            if row_id:
                MedExamDetail.objects.update_or_create(id=row_id, member_id=row["member_id"], defaults=defaults)
                continue
            MedExamDetail.objects.create(**defaults)
        logger.info("medical.sync.med_exam_details.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_medical_reports(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            medical_case_id = row.pop("medical_case", None) or row.pop("medical_case_id", None)
            if member_id:
                row["member_id"] = member_id
            if medical_case_id:
                row["medical_case_id"] = medical_case_id
            if not row.get("member_id"):
                continue
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                MedicalReport.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            MedicalReport.objects.create(**defaults)
        logger.info("medical.sync.medical_reports.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _record_model_change(
        self, *, user_id, member_id, entity, entity_id, action, from_status="", to_status="", changed_fields=None
    ):
        ModelChangeLog.objects.create(
            user_id=user_id,
            member_id=member_id,
            entity=entity,
            entity_id=entity_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            changed_fields=changed_fields or {},
        )

    def _upsert_prescription_batches(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            medical_case_id = row.pop("medical_case", None) or row.pop("medical_case_id", None)
            if member_id:
                row["member_id"] = member_id
            if medical_case_id:
                row["medical_case_id"] = medical_case_id
            if not row.get("member_id"):
                continue
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                obj, _ = PrescriptionBatch.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                self._record_model_change(
                    user_id=user_id,
                    member_id=obj.member_id,
                    entity="PrescriptionBatch",
                    entity_id=obj.id,
                    action="upsert",
                    to_status=obj.status,
                )
                continue
            obj = PrescriptionBatch.objects.create(**defaults)
            self._record_model_change(
                user_id=user_id,
                member_id=obj.member_id,
                entity="PrescriptionBatch",
                entity_id=obj.id,
                action="create",
                to_status=obj.status,
            )
        logger.info("medical.sync.prescription_batches.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_medications(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            batch_id = row.pop("batch", None) or row.pop("batch_id", None)
            if member_id:
                row["member_id"] = member_id
            if batch_id:
                row["batch_id"] = batch_id
            if not row.get("member_id") or not row.get("batch_id"):
                continue
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                obj, _ = Medication.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                self._record_model_change(
                    user_id=user_id,
                    member_id=obj.member_id,
                    entity="Medication",
                    entity_id=obj.id,
                    action="upsert",
                )
                continue
            obj = Medication.objects.create(**defaults)
            self._record_model_change(
                user_id=user_id,
                member_id=obj.member_id,
                entity="Medication",
                entity_id=obj.id,
                action="create",
            )
        logger.info("medical.sync.medications.upserted", extra={"user_id": user_id, "record_count": len(rows)})

    def _upsert_medication_taken_records(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            member_id = row.pop("member", None) or row.pop("member_id", None)
            medication_id = row.pop("medication", None) or row.pop("medication_id", None)
            if member_id:
                row["member_id"] = member_id
            if medication_id:
                row["medication_id"] = medication_id
            if not row.get("member_id") or not row.get("medication_id"):
                continue
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                obj, _ = MedicationTakenRecord.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                self._record_model_change(
                    user_id=user_id,
                    member_id=obj.member_id,
                    entity="MedicationTakenRecord",
                    entity_id=obj.id,
                    action="upsert",
                    to_status=obj.status,
                )
                continue
            obj = MedicationTakenRecord.objects.create(**defaults)
            self._record_model_change(
                user_id=user_id,
                member_id=obj.member_id,
                entity="MedicationTakenRecord",
                entity_id=obj.id,
                action="create",
                to_status=obj.status,
            )
        logger.info(
            "medical.sync.medication_taken_records.upserted",
            extra={"user_id": user_id, "record_count": len(rows)},
        )

    def _upsert_health_metrics(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row_id = row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            defaults = {**row, "user_id": user_id, "is_deleted": False}
            if row_id:
                HealthMetricRecord.objects.update_or_create(id=row_id, user_id=user_id, defaults=defaults)
                continue
            HealthMetricRecord.objects.create(**defaults)
        logger.info("medical.sync.health_metrics.upserted", extra={"user_id": user_id, "record_count": len(rows)})
