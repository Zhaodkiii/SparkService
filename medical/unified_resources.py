"""
Unified medical resource CRUD entry: /api/v1/medical/resources/?kind=<kind>

Delegates to existing WrappedModelViewSet subclasses so behavior matches per-resource REST routes.
"""

from __future__ import annotations

import io
import json

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated

from common.response import error_response

# kind -> ViewSet class (must match medical/urls.py resources)
MEDICAL_UNIFIED_RESOURCE_VIEWSETS: dict[str, type] = {}

# kind -> allowed query param names (excluding "kind")
MEDICAL_UNIFIED_ALLOWED_QUERY_PARAMS: dict[str, frozenset[str]] = {
    "members": frozenset(),
    "cases": frozenset({"member_id"}),
    "symptoms": frozenset({"member_id", "medical_case_id"}),
    "visits": frozenset({"member_id", "medical_case_id"}),
    "surgeries": frozenset({"member_id", "medical_case_id"}),
    "follow-ups": frozenset({"member_id", "medical_case_id"}),
    "health-exam-reports": frozenset({"member_id"}),
    "examination-reports": frozenset({"member_id"}),
    "med-exam-details": frozenset({"member_id", "business_type", "business_id"}),
    "prescription-batches": frozenset({"member_id", "medical_case_id"}),
    "medications": frozenset({"member_id", "batch_id"}),
    "medication-taken-records": frozenset({"member_id", "medication_id"}),
    "health-metrics": frozenset({"profile_client_uid"}),
}


def _register_unified_resources() -> None:
    # Late import avoids circular imports with medical.views
    from medical import views as medical_views

    global MEDICAL_UNIFIED_RESOURCE_VIEWSETS
    MEDICAL_UNIFIED_RESOURCE_VIEWSETS = {
        "members": medical_views.MemberViewSet,
        "cases": medical_views.MedicalCaseViewSet,
        "symptoms": medical_views.SymptomViewSet,
        "visits": medical_views.VisitViewSet,
        "surgeries": medical_views.SurgeryViewSet,
        "follow-ups": medical_views.FollowUpViewSet,
        "health-exam-reports": medical_views.HealthExamReportViewSet,
        "examination-reports": medical_views.ExaminationReportViewSet,
        "med-exam-details": medical_views.MedExamDetailViewSet,
        "prescription-batches": medical_views.PrescriptionBatchViewSet,
        "medications": medical_views.MedicationViewSet,
        "medication-taken-records": medical_views.MedicationTakenRecordViewSet,
        "health-metrics": medical_views.HealthMetricRecordViewSet,
    }


def _unknown_query_keys(request, allowed: frozenset[str]) -> list[str]:
    keys = set(request.query_params.keys())
    keys.discard("kind")
    return sorted(keys - allowed)


def _validate_kind(kind: str | None):
    if not kind or not isinstance(kind, str):
        return error_response(
            msg="kind_required",
            code=-1,
            status_code=status.HTTP_400_BAD_REQUEST,
            data={"detail": "Query parameter 'kind' is required and must be a non-empty string."},
        )
    if kind not in MEDICAL_UNIFIED_RESOURCE_VIEWSETS:
        return error_response(
            msg="invalid_kind",
            code=-1,
            status_code=status.HTTP_400_BAD_REQUEST,
            data={
                "detail": "Unknown resource kind.",
                "allowed_kinds": sorted(MEDICAL_UNIFIED_RESOURCE_VIEWSETS.keys()),
            },
        )
    return None


def _validate_query_params(request, kind: str):
    allowed = MEDICAL_UNIFIED_ALLOWED_QUERY_PARAMS.get(kind, frozenset())
    unknown = _unknown_query_keys(request, allowed)
    if unknown:
        return error_response(
            msg="invalid_query_params",
            code=-1,
            status_code=status.HTTP_400_BAD_REQUEST,
            data={
                "detail": "One or more query parameters are not allowed for this kind.",
                "unknown_params": unknown,
                "allowed_params": sorted(allowed),
            },
        )
    return None


def _normalize_examination_report_payload(data: dict) -> dict:
    out = dict(data)
    if "medical_record" not in out and "medical_case" in out:
        out["medical_record"] = out.pop("medical_case")
    return out


def _rewrite_json_body_for_examination_report(request):
    """Map medical_case -> medical_record in JSON body; refresh DRF parse cache."""
    try:
        payload = dict(request.data)
    except Exception:
        payload = request.data if isinstance(request.data, dict) else {}
    payload = _normalize_examination_report_payload(payload)
    body = json.dumps(payload).encode("utf-8")
    django_req = request._request
    django_req._body = body
    django_req._stream = io.BytesIO(body)
    django_req._read_started = False
    django_req.META["CONTENT_LENGTH"] = str(len(body))
    for attr in ("_full_data", "_data", "_files"):
        if hasattr(request, attr):
            try:
                delattr(request, attr)
            except AttributeError:
                pass


class UnifiedMedicalResourceViewSet(viewsets.ViewSet):
    """
    GET/POST    /api/v1/medical/resources/?kind=<kind>[&filters...]
    GET/PATCH/DELETE /api/v1/medical/resources/<pk>/?kind=<kind>[&filters...]
    """

    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        if not MEDICAL_UNIFIED_RESOURCE_VIEWSETS:
            _register_unified_resources()
        super().initial(request, *args, **kwargs)

    def _delegate(self, request, kind: str, actions: dict[str, str], pk=None):
        # Inner ViewSet.as_view() expects a Django HttpRequest; passing a nested
        # rest_framework.request.Request breaks initialize_request().
        django_request = getattr(request, "_request", request)
        viewset_cls = MEDICAL_UNIFIED_RESOURCE_VIEWSETS[kind]
        view = viewset_cls.as_view(actions)
        if pk is not None:
            return view(django_request, pk=pk)
        return view(django_request)

    def list(self, request):
        kind = request.query_params.get("kind")
        err = _validate_kind(kind)
        if err is not None:
            return err
        assert kind is not None
        err = _validate_query_params(request, kind)
        if err is not None:
            return err
        return self._delegate(request, kind, {"get": "list"})

    def create(self, request):
        kind = request.query_params.get("kind")
        err = _validate_kind(kind)
        if err is not None:
            return err
        assert kind is not None
        err = _validate_query_params(request, kind)
        if err is not None:
            return err
        if kind == "examination-reports":
            _rewrite_json_body_for_examination_report(request)
        return self._delegate(request, kind, {"post": "create"})

    def retrieve(self, request, pk=None):
        kind = request.query_params.get("kind")
        err = _validate_kind(kind)
        if err is not None:
            return err
        assert kind is not None
        err = _validate_query_params(request, kind)
        if err is not None:
            return err
        return self._delegate(request, kind, {"get": "retrieve"}, pk=str(pk))

    def partial_update(self, request, pk=None):
        kind = request.query_params.get("kind")
        err = _validate_kind(kind)
        if err is not None:
            return err
        assert kind is not None
        err = _validate_query_params(request, kind)
        if err is not None:
            return err
        if kind == "examination-reports":
            _rewrite_json_body_for_examination_report(request)
        return self._delegate(request, kind, {"patch": "partial_update"}, pk=str(pk))

    def update(self, request, pk=None):
        kind = request.query_params.get("kind")
        err = _validate_kind(kind)
        if err is not None:
            return err
        assert kind is not None
        err = _validate_query_params(request, kind)
        if err is not None:
            return err
        if kind == "examination-reports":
            _rewrite_json_body_for_examination_report(request)
        return self._delegate(request, kind, {"put": "update"}, pk=str(pk))

    def destroy(self, request, pk=None):
        kind = request.query_params.get("kind")
        err = _validate_kind(kind)
        if err is not None:
            return err
        assert kind is not None
        err = _validate_query_params(request, kind)
        if err is not None:
            return err
        return self._delegate(request, kind, {"delete": "destroy"}, pk=str(pk))


# Populate registry on module import (after medical.views is loadable)
_register_unified_resources()
