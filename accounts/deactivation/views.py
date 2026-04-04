import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import success_response
from accounts.deactivation.serializers import AccountDeactivationRequestSerializer
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

        result = DeactivationService.request_deactivation(
            user=request.user,
            request_id=request_id,
        )

        if not result.get("reused", False):
            deactivation_id = result["deactivation_id"]
            # Enqueue async processing immediately for new requests only.
            process_deactivation_task.delay(deactivation_id, request_id)
            flow_logger.info(
                "account.deactivation.task.enqueued",
                extra={"action": "account.deactivation.request", "request_id": request_id, "deactivation_id": deactivation_id, "reused": False},
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
