from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import success_response
from common.exceptions import APIError
from . import services
from .models import ProductionTask


class StartInput(serializers.Serializer):
    attempt_key = serializers.UUIDField()
    input_digest = serializers.RegexField(r"^[a-f0-9]{64}$")


class ActionInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


def payload(task):
    return {
        "id": str(task.pk), "state": task.state, "version": task.version,
        "attempt_key": str(task.attempt_key), "expires_at": task.expires_at.isoformat(),
        "result": task.result,
    }


class QuotaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        result = services.quota(request.user)
        result["entitled"] = bool(request.user.is_authenticated and request.user.is_active)
        result["can_start"] = result["can_start"] and result["entitled"]
        if not result["entitled"]:
            result["blocked_reasons"].append("entitlement_required")
            result["next_eligible_at"] = None
        return success_response(result)


class TaskListView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = StartInput(data=request.data)
        data.is_valid(raise_exception=True)
        existing = ProductionTask.objects.filter(
            account=request.user, attempt_key=data.validated_data["attempt_key"],
        ).exists()
        if not existing and not bool(request.user.is_authenticated and request.user.is_active):
            raise APIError("当前账号暂无 AI 制作权益", code=40301, status_code=403)
        return success_response(payload(services.start(request.user, **data.validated_data)))


class TaskDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        task = ProductionTask.objects.filter(account=request.user, pk=task_id).first()
        if task is None:
            raise APIError("制作任务不存在", status_code=404)
        return success_response(payload(task))


class TaskActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id, action):
        if action not in ("pause", "resume", "cancel"):
            raise APIError("不支持此操作", status_code=404)
        data = ActionInput(data=request.data)
        data.is_valid(raise_exception=True)
        task = ProductionTask.objects.filter(account=request.user, pk=task_id).first()
        if task and action == "resume" and (
            task.state == "expired" or task.expires_at <= services.timezone.now()
        ) and not bool(request.user.is_authenticated and request.user.is_active):
            raise APIError("当前账号暂无 AI 制作权益", code=40301, status_code=403)
        return success_response(payload(services.transition(
            request.user, task_id, action, data.validated_data["version"],
        )))


class TaskCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        class Input(serializers.Serializer):
            digest = serializers.RegexField(r"^[a-f0-9]{64}$")
        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        if not ProductionTask.objects.filter(account=request.user, pk=task_id).exists():
            raise APIError("制作任务不存在", status_code=404)
        task = services.settle_verified_result(
            request.user, task_id, {"digest": data.validated_data["digest"]})
        return success_response(payload(task))
