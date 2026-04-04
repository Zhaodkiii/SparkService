from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.http_cache import build_etag, normalize_etag
from common.response import success_response
from medical.models import ExaminationReport, HealthMetricRecord, MedicalCase, MedicalReport, Member, Prescription
from medical.serializers import (
    ExaminationReportSerializer,
    HealthMetricRecordSerializer,
    MedicalCaseSerializer,
    MedicalReportSerializer,
    MedicalSnapshotUploadSerializer,
    MemberSerializer,
    PrescriptionSerializer,
)


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


class ExaminationReportViewSet(WrappedModelViewSet):
    queryset = ExaminationReport.objects.select_related("member", "medical_case").all()
    serializer_class = ExaminationReportSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
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


class PrescriptionViewSet(WrappedModelViewSet):
    queryset = Prescription.objects.select_related("member", "medical_case").all()
    serializer_class = PrescriptionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
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
        examination_reports = list(ExaminationReport.objects.filter(user=request.user, is_deleted=False).values())
        medical_reports = list(MedicalReport.objects.filter(user=request.user, is_deleted=False).values())
        prescriptions = list(Prescription.objects.filter(user=request.user, is_deleted=False).values())
        health_metrics = list(HealthMetricRecord.objects.filter(user=request.user, is_deleted=False).values())

        payload = {
            "members": members,
            "medical_cases": medical_cases,
            "examination_reports": examination_reports,
            "medical_reports": medical_reports,
            "prescriptions": prescriptions,
            "health_metrics": [],
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
            "examination_reports": signature_for(ExaminationReport),
            "medical_reports": signature_for(MedicalReport),
            "prescriptions": signature_for(Prescription),
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
        self._upsert_examination_reports(request.user.id, payload.get("examination_reports", []))
        self._upsert_medical_reports(request.user.id, payload.get("medical_reports", []))
        self._upsert_prescriptions(request.user.id, payload.get("prescriptions", []))
        self._upsert_health_metrics(request.user.id, payload.get("health_metrics", []))

        return success_response({"uploaded": True}, msg="uploaded", code=0, status_code=status.HTTP_200_OK)

    def _upsert_members(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            client_uid = row.get("client_uid")
            if not client_uid:
                continue
            Member.objects.update_or_create(
                user_id=user_id,
                client_uid=client_uid,
                defaults={**row, "user_id": user_id, "is_deleted": False},
            )

    def _upsert_medical_cases(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            client_uid = row.get("client_uid")
            if not client_uid:
                continue
            member_client_uid = row.pop("member_client_uid", None)
            if member_client_uid and not row.get("member"):
                member = Member.objects.filter(user_id=user_id, client_uid=member_client_uid, is_deleted=False).first()
                if member:
                    row["member_id"] = member.id
            MedicalCase.objects.update_or_create(
                user_id=user_id,
                client_uid=client_uid,
                defaults={**row, "user_id": user_id, "is_deleted": False},
            )

    def _upsert_examination_reports(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            client_uid = row.get("client_uid")
            if not client_uid:
                continue
            member_client_uid = row.pop("member_client_uid", None)
            case_client_uid = row.pop("medical_case_client_uid", None)
            if member_client_uid and not row.get("member"):
                member = Member.objects.filter(user_id=user_id, client_uid=member_client_uid, is_deleted=False).first()
                if member:
                    row["member_id"] = member.id
            if case_client_uid and not row.get("medical_case"):
                medical_case = MedicalCase.objects.filter(user_id=user_id, client_uid=case_client_uid, is_deleted=False).first()
                if medical_case:
                    row["medical_case_id"] = medical_case.id
            ExaminationReport.objects.update_or_create(
                user_id=user_id,
                client_uid=client_uid,
                defaults={**row, "user_id": user_id, "is_deleted": False},
            )

    def _upsert_medical_reports(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            client_uid = row.get("client_uid")
            if not client_uid:
                continue
            member_client_uid = row.pop("member_client_uid", None)
            case_client_uid = row.pop("medical_case_client_uid", None)
            if member_client_uid and not row.get("member"):
                member = Member.objects.filter(user_id=user_id, client_uid=member_client_uid, is_deleted=False).first()
                if member:
                    row["member_id"] = member.id
            if case_client_uid and not row.get("medical_case"):
                medical_case = MedicalCase.objects.filter(user_id=user_id, client_uid=case_client_uid, is_deleted=False).first()
                if medical_case:
                    row["medical_case_id"] = medical_case.id
            MedicalReport.objects.update_or_create(
                user_id=user_id,
                client_uid=client_uid,
                defaults={**row, "user_id": user_id, "is_deleted": False},
            )

    def _upsert_prescriptions(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            client_uid = row.get("client_uid")
            if not client_uid:
                continue
            member_client_uid = row.pop("member_client_uid", None)
            case_client_uid = row.pop("medical_case_client_uid", None)
            if member_client_uid and not row.get("member"):
                member = Member.objects.filter(user_id=user_id, client_uid=member_client_uid, is_deleted=False).first()
                if member:
                    row["member_id"] = member.id
            if case_client_uid and not row.get("medical_case"):
                medical_case = MedicalCase.objects.filter(user_id=user_id, client_uid=case_client_uid, is_deleted=False).first()
                if medical_case:
                    row["medical_case_id"] = medical_case.id
            Prescription.objects.update_or_create(
                user_id=user_id,
                client_uid=client_uid,
                defaults={**row, "user_id": user_id, "is_deleted": False},
            )

    def _upsert_health_metrics(self, user_id, rows):
        for row in rows:
            row = dict(row)
            row.pop("id", None)
            row.pop("created_at", None)
            row.pop("updated_at", None)
            client_uid = row.get("client_uid")
            if not client_uid:
                continue
            HealthMetricRecord.objects.update_or_create(
                user_id=user_id,
                client_uid=client_uid,
                defaults={**row, "user_id": user_id, "is_deleted": False},
            )
