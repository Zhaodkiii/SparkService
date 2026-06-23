import logging

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import error_response, success_response
from medical.models import HealthExamReport, Member, Symptom
from medical.serializers import MemberMedicalProfileSerializer
from medical.services.exam_archive_service import (
    build_evidence_snapshot,
    build_follow_up_tasks_from_abnormals,
    extract_abnormal_items_from_report,
    generate_exam_archive_ai_plan,
    save_confirmed_abnormal_items,
)
from medical.services.member_medical_profile_service import (
    build_member_medical_guidance_projection,
    enrich_member_medical_profile_payload,
)
from medical.services.member_permission_gate import MemberPermissionGate

logger = logging.getLogger(__name__)


class _MemberExamArchiveBaseAPI(APIView):
    permission_classes = [IsAuthenticated]

    def _resolve_member(self, request, member_id: int) -> Member | None:
        try:
            binding = MemberPermissionGate.require_access(user=request.user, member_id=member_id)
            return binding.member
        except PermissionError:
            return None
        except Member.DoesNotExist:
            return None

    def _resolve_report(self, member: Member, report_id: int | None) -> HealthExamReport | None:
        if not report_id:
            return None
        return (
            HealthExamReport.objects.filter(
                is_deleted=False,
                member_id=member.id,
                id=report_id,
            )
            .order_by("-id")
            .first()
        )

    def _profile_for_member(self, request, member: Member):
        from medical.models import MemberMedicalProfile

        return (
            MemberMedicalProfile.objects.filter(is_deleted=False, member_id=member.id, user=request.user)
            .order_by("-updated_at", "-id")
            .first()
        )

    def _build_response_envelope(self, request, member: Member, result: dict) -> dict:
        profile = result.get("profile")
        report = None
        source_report_id = result.get("source_report_id")
        if source_report_id:
            report = self._resolve_report(member, source_report_id)

        symptoms = list(Symptom.objects.filter(is_deleted=False, member_id=member.id).order_by("-created_at")[:20])
        guidance_projection = build_member_medical_guidance_projection(
            member=member,
            profile=profile,
            symptoms=symptoms,
            health_exam_reports=[report] if report else [],
        )
        profile_payload = None
        if profile is not None:
            base_profile = MemberMedicalProfileSerializer(profile, context={"request": request}).data
            profile_payload = enrich_member_medical_profile_payload(base_profile, guidance_projection)

        payload = dict(result)
        payload.pop("plan", None)
        payload.pop("profile", None)
        payload["member_medical_profile"] = profile_payload
        payload["guidance_sections"] = guidance_projection.get("guidance_sections") or []
        return payload


class MemberExamArchivePreviewAbnormalItemsAPI(_MemberExamArchiveBaseAPI):
    """POST /members/{member_id}/exam-archive/preview-abnormal-items/"""

    def post(self, request, member_id: int):
        member = self._resolve_member(request, member_id)
        if member is None:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)

        report_id = request.data.get("health_exam_report_id")
        if not report_id:
            return error_response(msg="health_exam_report_id_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        report = self._resolve_report(member, int(report_id))
        if report is None:
            return error_response(msg="report_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        abnormal_items = extract_abnormal_items_from_report(report=report)
        follow_up_tasks = build_follow_up_tasks_from_abnormals(abnormal_items)
        logger.info(
            "preview-abnormal-items member_id=%s report_id=%s count=%s",
            member.id,
            report.id,
            len(abnormal_items),
        )
        return success_response(
            {
                "member_id": member.id,
                "health_exam_report_id": report.id,
                "abnormal_items": abnormal_items,
                "follow_up_tasks": follow_up_tasks,
            }
        )


class MemberExamArchiveConfirmedAbnormalItemsAPI(_MemberExamArchiveBaseAPI):
    """POST /members/{member_id}/exam-archive/confirmed-abnormal-items/"""

    @transaction.atomic
    def post(self, request, member_id: int):
        member = self._resolve_member(request, member_id)
        if member is None:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)

        report_id = request.data.get("health_exam_report_id")
        abnormal_items = request.data.get("selected_abnormal_items") or request.data.get("abnormal_items") or []
        if not isinstance(abnormal_items, list):
            return error_response(msg="invalid_abnormal_items", code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        report = self._resolve_report(member, int(report_id)) if report_id else None
        record = save_confirmed_abnormal_items(
            user=request.user,
            member=member,
            report=report,
            abnormal_items=abnormal_items,
        )
        follow_up_tasks = build_follow_up_tasks_from_abnormals(abnormal_items)
        return success_response(
            {
                "member_id": member.id,
                "record_id": record.id,
                "abnormal_items": abnormal_items,
                "follow_up_tasks": follow_up_tasks,
            }
        )


class MemberExamArchiveEvidenceAPI(_MemberExamArchiveBaseAPI):
    """GET /members/{member_id}/exam-archive/evidence/ — 无报告模式画像依据。"""

    def get(self, request, member_id: int):
        member = self._resolve_member(request, member_id)
        if member is None:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)

        profile = self._profile_for_member(request, member)
        symptoms = list(Symptom.objects.filter(is_deleted=False, member_id=member.id).order_by("-created_at")[:20])
        evidence = build_evidence_snapshot(member=member, profile=profile, symptoms=symptoms)
        return success_response({"member_id": member.id, "evidence": evidence})


class MemberExamArchiveAIPlanAPI(_MemberExamArchiveBaseAPI):
    """POST /members/{member_id}/exam-archive/ai-plan/"""

    @transaction.atomic
    def post(self, request, member_id: int):
        member = self._resolve_member(request, member_id)
        if member is None:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)

        mode = str(request.data.get("mode") or "report_based")
        if mode not in {"report_based", "baseline"}:
            return error_response(msg="invalid_mode", code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        report_id = request.data.get("health_exam_report_id")
        report = self._resolve_report(member, int(report_id)) if report_id else None
        if mode == "report_based" and report is None:
            return error_response(msg="report_not_found", code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        selected_abnormal_items = request.data.get("selected_abnormal_items")
        create_follow_up_tasks_flag = bool(request.data.get("create_follow_up_tasks"))
        selected_follow_up_task_keys = request.data.get("selected_follow_up_task_keys") or []
        client_plan_payload = request.data.get("exam_plan")
        ai_trace_id = str(request.data.get("ai_trace_id") or "")
        model_name = str(request.data.get("model_name") or "")

        logger.info(
            "exam-plan start member_id=%s mode=%s report_id=%s",
            member.id,
            mode,
            report.id if report else None,
        )

        try:
            result = generate_exam_archive_ai_plan(
                user=request.user,
                member=member,
                mode=mode,
                report=report,
                selected_abnormal_items=selected_abnormal_items,
                create_follow_up_tasks_flag=create_follow_up_tasks_flag,
                selected_follow_up_task_keys=selected_follow_up_task_keys,
                client_plan_payload=client_plan_payload,
                ai_trace_id=ai_trace_id,
                model_name=model_name,
            )
        except Exception as exc:
            logger.exception("exam-plan failed member_id=%s error=%s", member.id, exc)
            return error_response(msg="exam_plan_generation_failed", code=-1, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.info(
            "exam-plan AI success member_id=%s plan_id=%s must=%s recommended=%s followUp=%s",
            member.id,
            result.get("plan_id"),
            len((result.get("exam_plan") or {}).get("must_items") or []),
            len((result.get("exam_plan") or {}).get("recommended_items") or []),
            len((result.get("exam_plan") or {}).get("follow_up_items") or []),
        )

        payload = self._build_response_envelope(request, member, result)
        return success_response(payload)
