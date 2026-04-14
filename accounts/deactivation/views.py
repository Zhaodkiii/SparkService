import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import success_response
from accounts.deactivation.serializers import AccountDeactivationCancelSerializer, AccountDeactivationRequestSerializer
from accounts.models import AccountDeactivation
from accounts.services.deactivation_service import DeactivationService
from accounts.deactivation.tasks import process_deactivation_task

flow_logger = logging.getLogger("accounts.flow")


class AccountDeactivationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "account.deactivation.status.begin",
            extra={"action": "account.deactivation.status", "path": request.path, "method": request.method, "request_id": request_id},
        )
        deactivation_id = request.query_params.get("deactivation_id")
        if not deactivation_id:
            flow_logger.warning(
                "account.deactivation.status.failed",
                extra={"action": "account.deactivation.status", "request_id": request_id, "reason": "missing_deactivation_id"},
            )
            return success_response(data=None, msg="missing deactivation_id", code=0, status_code=status.HTTP_200_OK)

        obj = AccountDeactivation.objects.filter(id=deactivation_id, user_id=request.user.id).first()
        if not obj:
            flow_logger.warning(
                "account.deactivation.status.not_found",
                extra={"action": "account.deactivation.status", "request_id": request_id, "deactivation_id": deactivation_id},
            )
            return success_response(data=None, msg="not found", code=0, status_code=status.HTTP_200_OK)

        flow_logger.info(
            "account.deactivation.status.success",
            extra={
                "action": "account.deactivation.status",
                "request_id": request_id,
                "deactivation_id": obj.id,
                "state": obj.state,
                "user_id": request.user.id,
            },
        )
        return success_response(
            {"deactivation_id": obj.id, "state": obj.state, "scheduled_at": obj.scheduled_at, "completed_at": obj.completed_at},
            msg="deactivation_status",
            code=0,
            status_code=status.HTTP_200_OK,
        )

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "account.deactivation.request.begin",
            extra={"action": "account.deactivation.request", "path": request.path, "method": request.method, "request_id": request_id, "user_id": request.user.id},
        )
        serializer = AccountDeactivationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        immediate_deactivation = serializer.validated_data.get("immediate_deactivation", True)
        countdown_hours = serializer.validated_data.get("countdown_hours", 0)

        result = DeactivationService.request_deactivation(
            user=request.user,
            request_id=request_id,
            immediate_deactivation=immediate_deactivation,
            countdown_hours=countdown_hours,
        )

        if not result.get("reused", False):
            deactivation_id = result["deactivation_id"]
            if immediate_deactivation:
                process_deactivation_task.delay(deactivation_id, request_id)
            else:
                process_deactivation_task.apply_async(args=[deactivation_id, request_id], countdown=max(1, int(countdown_hours)) * 3600)
            flow_logger.info(
                "account.deactivation.task.enqueued",
                extra={
                    "action": "account.deactivation.request",
                    "request_id": request_id,
                    "deactivation_id": deactivation_id,
                    "reused": False,
                    "immediate_deactivation": immediate_deactivation,
                    "countdown_hours": countdown_hours,
                },
            )
        else:
            flow_logger.info(
                "account.deactivation.request.reused",
                extra={"action": "account.deactivation.request", "request_id": request_id, "deactivation_id": result.get("deactivation_id"), "reused": True},
            )

        return success_response(
            result,
            msg="deactivation_requested",
            code=0,
            status_code=status.HTTP_202_ACCEPTED,
        )

    def delete(self, request):
        request_id = getattr(request, "request_id", "") or ""
        deactivation_id = request.query_params.get("deactivation_id")
        if not deactivation_id or not str(deactivation_id).isdigit():
            return success_response(data=None, msg="missing deactivation_id", code=0, status_code=status.HTTP_200_OK)

        serializer = AccountDeactivationCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = DeactivationService.cancel_deactivation(
            deactivation_id=int(deactivation_id),
            user_id=request.user.id,
            request_id=request_id,
            reason=serializer.validated_data.get("reason", ""),
        )
        return success_response(result, msg="deactivation_cancelled", code=0, status_code=status.HTTP_200_OK)
