from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import success_response
from common.exceptions import APIError
from . import services
from .models import ProductionTask


class StartInput(serializers.Serializer):
    usage_metering = serializers.BooleanField(required=False, write_only=True)
    attempt_key = serializers.UUIDField()
    input_digest = serializers.RegexField(r"^[a-f0-9]{64}$")
    from ai_runtime.views import CapInput
    client_capabilities = CapInput()
    required_scenes = serializers.ListField(child=serializers.ChoiceField(choices=[
        "diary.layout", "diary.background.design", "diary.background.generate", "diary.background.review"
    ]), min_length=1, max_length=4)


class ActionInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


def payload(task):
    return {
        "id": str(task.pk), "state": task.state, "version": task.version,
        "attempt_key": str(task.attempt_key),
        "result": task.result,
    }


class QuotaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success_response(services.quota(request.user))


class TaskListView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = StartInput(data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data.pop("usage_metering", False) is not True:
            raise APIError("请更新客户端后开始制作", status_code=426)
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
        return success_response(payload(services.transition(
            request.user, task_id, action, data.validated_data["version"],
        )))


class TaskCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        class Input(serializers.Serializer):
            digest = serializers.RegexField(r"^[a-f0-9]{64}$")
            page_id = serializers.UUIDField(required=False)
            faces = serializers.ListField(child=serializers.ChoiceField(choices=["left","right"]), max_length=2, required=False)
        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        if not ProductionTask.objects.filter(account=request.user, pk=task_id).exists():
            raise APIError("制作任务不存在", status_code=404)
        task = services.complete(
            request.user, task_id, dict(digest=data.validated_data["digest"], **(
                {"page_id": str(data.validated_data["page_id"]), "faces": sorted(set(data.validated_data["faces"]))}
                if data.validated_data.get("page_id") and data.validated_data.get("faces") else {})))
        return success_response(payload(task))


class CallInput(serializers.Serializer):
    call_id = serializers.UUIDField()
    scene = serializers.CharField(max_length=64)
    input_digest = serializers.RegexField(r"^[a-f0-9]{64}$")
    parameters = serializers.DictField()


class UsageInput(serializers.Serializer):
    input_tokens = serializers.IntegerField(min_value=0, max_value=100000000, required=False)
    cached_input_tokens = serializers.IntegerField(min_value=0, max_value=100000000, required=False)
    output_tokens = serializers.IntegerField(min_value=0, max_value=100000000, required=False)
    generated_images = serializers.IntegerField(min_value=0, max_value=1000, required=False)


class ReportInput(serializers.Serializer):
    event_id = serializers.UUIDField()
    execution_state = serializers.ChoiceField(choices=["completed", "failed", "cancelled", "unknown"])
    usage = UsageInput(required=False, default=dict)
    provider_request_id = serializers.CharField(max_length=200, allow_blank=True, default="")


def call_payload(call):
    return dict(call_id=str(call.pk), execution_state=call.execution_state, accounting_state=call.accounting_state,
                usage_due_at=call.usage_due_at.isoformat(), estimated=call.accounting_state == "estimated")


class CallListView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        data = CallInput(data=request.data)
        data.is_valid(raise_exception=True)
        return success_response(call_payload(services.authorize(request.user, task_id, **data.validated_data)))


class CallDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id, call_id):
        services.expire_account_calls(request.user)
        return success_response(call_payload(services.get_call(request.user, task_id, call_id)))


class CallUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id, call_id):
        data = ReportInput(data=request.data)
        data.is_valid(raise_exception=True)
        call = services.report(request.user, task_id, call_id, **data.validated_data)
        return success_response({**call_payload(call), "quota": services.quota(request.user)})
