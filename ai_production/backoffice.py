from django.db import transaction
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from rest_framework.views import APIView
from common.permissions import AdminCodePermission
from common.response import success_response
from backoffice.audit import write_audit_log
from .models import ProductionControl, ProductionPolicy, ProductionTask, ProductionLedger
from .views import payload


class PolicyInput(serializers.ModelSerializer):
    class Meta:
        model = ProductionPolicy
        fields = ("id", "publish_key", "name", "effective_at", "short_limit", "weekly_limit", "hold_hours", "enabled", "reason")
        read_only_fields = ("id",)
        extra_kwargs = {"publish_key": {"validators": []}}

    def validate_hold_hours(self, value):
        if not 1 <= value <= 168:
            raise serializers.ValidationError("保留时间需为 1 至 168 小时")
        return value


class ProductionAdminView(APIView):
    permission_classes = [AdminCodePermission]
    @property
    def required_permission_code(self):
        return "button:ai:production:publish" if self.request.method == "POST" else "menu:ai:production"

    def get(self, request):
        from .services import quota
        class Query(serializers.Serializer):
            account = serializers.IntegerField(min_value=1, required=False)
            page = serializers.IntegerField(min_value=1, default=1)
            page_size = serializers.IntegerField(min_value=1, max_value=100, default=25)
            state = serializers.ChoiceField(choices=["reserved", "paused", "completed", "cancelled", "expired"], required=False)
            task_id = serializers.UUIDField(required=False)
        query = Query(data={k: v for k, v in request.query_params.items() if v})
        query.is_valid(raise_exception=True)
        values = query.validated_data
        tasks = ProductionTask.objects.order_by("-created_at", "-pk")
        if values.get("account"):
            tasks = tasks.filter(account_id=values["account"])
        if values.get("state"):
            tasks = tasks.filter(state=values["state"])
        if values.get("task_id"):
            tasks = tasks.filter(pk=values["task_id"])
        paginator = Paginator(tasks, values["page_size"])
        page = paginator.get_page(values["page"])
        policies = ProductionPolicy.objects.order_by("-effective_at", "-pk")[:50]
        current = ProductionPolicy.objects.filter(effective_at__lte=timezone.now()).order_by("-effective_at", "-pk").first()
        account_quota = None
        if values.get("account"):
            user = get_user_model().objects.filter(pk=values["account"]).first()
            if user is None:
                raise serializers.ValidationError("账户不存在")
            account_quota = quota(user)
        ledger = ProductionLedger.objects.order_by("-created_at")
        if values.get("account"):
            ledger = ledger.filter(task__account_id=values["account"])
        return success_response({
            "service_control": dict(ProductionControl.objects.filter(pk=1).values("accepting", "version", "reason").first() or {"accepting": True, "version": 0, "reason": ""}),
            "server_time": timezone.now().isoformat(),
            "current_policy": PolicyInput(current).data if current else None,
            "policies": PolicyInput(policies, many=True).data,
            "account_quota": account_quota,
            "tasks": [{**payload(t), "account": t.account_id, "created_at": t.created_at.isoformat()} for t in page],
            "pagination": {"total": paginator.count, "page": page.number, "page_size": values["page_size"]},
            "ledger": [{"id": row.pk, "task_id": str(row.task_id), "event": row.event,
                        "reason": row.reason, "created_at": row.created_at.isoformat(),
                        "actor": row.actor_id} for row in ledger[:100]],
        })

    @transaction.atomic
    def post(self, request):
        data = PolicyInput(data=request.data)
        data.is_valid(raise_exception=True)
        from .services import lock_account
        lock_account(request.user)
        key = data.validated_data.get("publish_key")
        if key:
            existing = ProductionPolicy.objects.filter(publish_key=key).first()
            if existing:
                for field, value in data.validated_data.items():
                    if getattr(existing, field) != value:
                        raise serializers.ValidationError("发布内容已改变，请重新预览")
                return success_response(PolicyInput(existing).data)
        policy = data.save()
        write_audit_log(request, action="production.policy.publish",
                        resource_type="production_policy", resource_id=str(policy.pk),
                        response_payload=data.data)
        return success_response(data.data)


class RefundInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=False)


class ProductionRefundView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:production:refund"

    def post(self, request, task_id):
        from .services import refund
        from common.exceptions import APIError
        data = RefundInput(data=request.data)
        data.is_valid(raise_exception=True)
        if not ProductionTask.objects.filter(pk=task_id).exists():
            raise APIError("制作任务不存在", status_code=404)
        task = refund(request.user, task_id, data.validated_data["reason"])
        write_audit_log(request, action="production.refund", resource_type="production_task",
                        resource_id=str(task.pk))
        return success_response(payload(task))


class ProductionReleaseView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:production:release"

    def post(self, request, task_id):
        from django.db import transaction
        from common.exceptions import APIError
        from .services import lock_account, release
        data = RefundInput(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            target = ProductionTask.objects.filter(pk=task_id).first()
            if target is None:
                raise APIError("制作任务不存在", status_code=404)
            lock_account(target.account)
            task = ProductionTask.objects.select_related("short_window", "weekly_window").get(pk=task_id)
            if task.state in ("reserved", "paused"):
                release(task, "cancelled", request.user, data.validated_data["reason"])
            elif task.state not in ("cancelled", "expired"):
                raise APIError("该任务已结算，请使用退回次数", status_code=409)
            write_audit_log(request, action="production.release", resource_type="production_task",
                            resource_id=str(task.pk))
        return success_response(payload(task))


class ProductionControlView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:production:control"

    @transaction.atomic
    def post(self, request):
        class Input(serializers.Serializer):
            accepting = serializers.BooleanField()
            version = serializers.IntegerField(min_value=0)
            reason = serializers.CharField(max_length=500)
        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        # The singleton is seeded by migration, so the lock exists before concurrent requests.
        control = ProductionControl.objects.select_for_update().get(pk=1)
        if control.version != values["version"]:
            from common.exceptions import APIError
            raise APIError("服务状态已改变，请刷新", status_code=409)
        control.accepting = values["accepting"]
        control.reason = values["reason"]
        control.version += 1
        control.save()
        write_audit_log(request, action="production.control", resource_type="production_control",
                        resource_id="1", response_payload=values)
        return success_response({"accepting": control.accepting, "version": control.version})


class ProductionUsersView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "menu:ai:production"

    def get(self, request):
        from django.db.models import Q
        from .services import quota

        class Query(serializers.Serializer):
            page = serializers.IntegerField(min_value=1, default=1)
            page_size = serializers.IntegerField(min_value=1, max_value=100, default=25)
            q = serializers.CharField(required=False, allow_blank=True, max_length=100)

        query = Query(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        used_accounts = ProductionLedger.objects.filter(event__in=["reserve", "settle"]).values("task__account_id")
        users = get_user_model().objects.filter(
            is_active=True, pk__in=used_accounts,
        ).order_by("-id")
        term = values.get("q", "").strip()
        if term:
            match = Q(username__icontains=term)
            if term.isdigit():
                match |= Q(pk=int(term))
            users = users.filter(match)
        paginator = Paginator(users, values["page_size"])
        page = paginator.get_page(values["page"])
        items = []
        for user in page:
            snapshot = quota(user)
            items.append({
                "id": user.pk, "username": user.get_username(),
                "windows": snapshot["windows"], "can_start": snapshot["can_start"],
                "blocked_reasons": snapshot["blocked_reasons"],
            })
        return success_response({
            "items": items,
            "pagination": {"total": paginator.count, "page": page.number,
                           "page_size": values["page_size"]},
        })


class ProductionQuotaResetView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:production:reset"

    @transaction.atomic
    def post(self, request, user_id):
        from .services import reset_quota, quota
        from common.exceptions import APIError

        class Input(serializers.Serializer):
            request_key = serializers.UUIDField()
            scope = serializers.ChoiceField(choices=["short", "weekly", "both"])
            reason = serializers.CharField(max_length=500, trim_whitespace=True)
        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        user = get_user_model().objects.filter(pk=user_id).first()
        if user is None:
            raise APIError("账户不存在", status_code=404)
        reset = reset_quota(request.user, user, **data.validated_data)
        write_audit_log(request, action="production.quota.reset", resource_type="production_quota_reset",
                        resource_id=str(reset.pk),
                        response_payload={"account": user_id, "scope": reset.scope,
                                          "windows": reset.windows})
        return success_response({"reset_id": reset.pk, "quota": quota(user)})
