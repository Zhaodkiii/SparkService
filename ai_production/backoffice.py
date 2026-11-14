from decimal import Decimal, ROUND_HALF_UP
import json

from django.db import transaction
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from rest_framework.views import APIView
from common.permissions import AdminCodePermission
from common.response import success_response
from backoffice.audit import write_audit_log
from .models import ProductionControl, ProductionPolicy, ProductionCall, ProductionLedger
from common.exceptions import APIError
from .views import call_payload, UsageInput


class ModelRateInput(serializers.Serializer):
    category = serializers.ChoiceField(choices=["text_ai", "image_ai"])
    mode = serializers.ChoiceField(choices=["tokens", "images"])
    input_rate = serializers.DecimalField(max_digits=18, decimal_places=8, min_value=Decimal(0), default=Decimal(0))
    cached_input_rate = serializers.DecimalField(max_digits=18, decimal_places=8, min_value=Decimal(0), default=Decimal(0))
    output_rate = serializers.DecimalField(max_digits=18, decimal_places=8, min_value=Decimal(0), default=Decimal(0))
    minimum_charge = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"))
    max_input_tokens = serializers.IntegerField(min_value=1, max_value=10000000, default=128000)
    max_output_tokens = serializers.IntegerField(min_value=1, max_value=10000000, default=8192)
    max_images = serializers.IntegerField(min_value=1, max_value=100, default=1)
    image_rates = serializers.DictField(child=serializers.DecimalField(
        max_digits=18, decimal_places=8, min_value=Decimal("0.00000001"),
    ), default=dict)
    usage_timeout_seconds = serializers.IntegerField(min_value=360, max_value=3600, default=420)

    def validate(self, values):
        if values["category"] == "image_ai" and not values["image_rates"]:
            raise serializers.ValidationError("图片模型必须配置尺寸")
        if values["mode"] == "images" and values["category"] != "image_ai":
            raise serializers.ValidationError("文本模型须按 token 计量")
        if values["mode"] == "tokens" and not (values["input_rate"] or values["output_rate"]):
            raise serializers.ValidationError("至少配置一个非零 token 费率")
        return values


class PolicyInput(serializers.ModelSerializer):
    rates = serializers.DictField(child=ModelRateInput(), allow_empty=False)
    publish_key = serializers.UUIDField()
    free_weekly_limit_points = serializers.DecimalField(max_digits=24, decimal_places=6, min_value=Decimal("0.000001"))
    short_limit_points = serializers.DecimalField(max_digits=24, decimal_places=6, min_value=Decimal("0.000001"))
    weekly_limit_points = serializers.DecimalField(max_digits=24, decimal_places=6, min_value=Decimal("0.000001"))

    class Meta:
        model = ProductionPolicy
        fields = ("id", "publish_key", "name", "effective_at", "free_weekly_limit_points", "short_limit_points", "weekly_limit_points", "rates", "enabled", "reason")

    def validate(self, values):
        free = values["free_weekly_limit_points"]
        short = values["short_limit_points"]
        weekly = values["weekly_limit_points"]
        if not free <= short <= weekly or free >= weekly:
            raise serializers.ValidationError("积分上限须满足：免费 7 天 ≤ Pro 5 小时 ≤ Pro 7 天，且 Pro 7 天大于免费 7 天")
        return values

    def validate_rates(self, rates):
        result = {}
        for model, rate in rates.items():
            if not model.strip() or len(model) > 200:
                raise serializers.ValidationError("模型标识无效")
            result[model] = json.loads(json.dumps(rate, default=str))
        return result


def calls_page(queryset, request):
    class Query(serializers.Serializer):
        page = serializers.IntegerField(min_value=1, default=1)
        page_size = serializers.IntegerField(min_value=1, max_value=100, default=25)
    query = Query(data=request.query_params)
    query.is_valid(raise_exception=True)
    page = Paginator(queryset, query.validated_data["page_size"]).get_page(query.validated_data["page"])
    return page, dict(total=page.paginator.count, page=page.number, page_size=page.paginator.per_page)


def admin_call(call):
    return {**call_payload(call), "account": call.task.account_id, "task_id": str(call.task_id),
            "category": call.category, "scene": call.scene, "model": call.model,
            "points": str(call.charged_points), "source": call.usage_source,
            "created_at": call.created_at, "version": call.version,
            "plan_at_authorization": call.plan_at_authorization, "policy_version": call.policy_id}


class ProductionAdminView(APIView):
    permission_classes = [AdminCodePermission]

    @property
    def required_permission_code(self):
        return "button:ai:production:publish" if self.request.method == "POST" else "menu:ai:production"

    def get(self, request):
        from .services import current_policy
        policies = ProductionPolicy.objects.order_by("-effective_at", "-pk")[:50]
        current = current_policy(timezone.now())
        return success_response({
            "current_policy": PolicyInput(current).data if current else None,
            "policies": PolicyInput(policies, many=True).data,
            "service_control": ProductionControl.objects.filter(pk=1).values("accepting", "version", "reason").get(),
        })

    @transaction.atomic
    def post(self, request):
        data = PolicyInput(data=request.data)
        data.is_valid(raise_exception=True)
        ProductionControl.objects.select_for_update().get(pk=1)
        values = data.validated_data
        existing = ProductionPolicy.objects.filter(publish_key=values["publish_key"]).first()
        if existing:
            if any(getattr(existing, field) != value for field, value in values.items()):
                raise serializers.ValidationError("发布内容已改变")
            return success_response(PolicyInput(existing).data)
        from ai_runtime.models import Channel
        channel = Channel.objects.select_related("current").filter(pk=1).first()
        if values.get("enabled", True) and channel and channel.current:
            from .services import call_budget
            missing = set()
            too_large = []
            for name, scene in channel.current.snapshot["scenes"].items():
                model = scene["model_id"]
                category = "image_ai" if scene["adapter_id"] == "ark_images_v1" else "text_ai"
                rate = values["rates"].get(model)
                if not rate or rate["category"] != category:
                    missing.add(model)
                    continue
                params = scene["parameters"]
                if category == "image_ai" and params.get("size", "2K") not in rate["image_rates"]:
                    raise serializers.ValidationError({"rates": f"{name} 的图片尺寸未配置费率"})
                if category == "text_ai" and params.get("max_output_tokens", 0) > rate["max_output_tokens"]:
                    raise serializers.ValidationError({"rates": f"{name} 的输出 token 超出费率配置"})
                if call_budget(rate, params) > values["free_weekly_limit_points"]:
                    too_large.append(name)
            if too_large:
                raise serializers.ValidationError({"free_weekly_limit_points": "以下场景预算超过免费额度：" + "、".join(too_large)})
            if missing:
                raise serializers.ValidationError({"rates": "请配置已发布场景的模型费率：" + "、".join(sorted(missing))})
        policy = data.save()
        write_audit_log(request, action="production.policy.publish", resource_type="production_policy",
                        resource_id=str(policy.pk), response_payload=data.data)
        return success_response(data.data)


class ProductionCallsView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "menu:ai:production"

    def get(self, request, call_id=None):
        calls = ProductionCall.objects.select_related("task").order_by("-created_at", "-id")
        if call_id:
            call = calls.filter(pk=call_id).first()
            if not call:
                raise APIError("模型调用不存在", status_code=404)
            return success_response({
                **admin_call(call), "usage": call.usage, "rate": call.rate, "budget": str(call.budget),
                "provider_request_id": call.provider_request_id,
                "ledger": list(call.ledger.order_by("id").values(
                    "event", "delta_points", "resulting_points", "usage_source", "reason", "created_at",
                )),
            })
        class Query(serializers.Serializer):
            account = serializers.IntegerField(min_value=1, required=False)
            task_id = serializers.UUIDField(required=False)
            call_id = serializers.UUIDField(required=False)
            model = serializers.CharField(max_length=200, required=False)
            category = serializers.ChoiceField(choices=["text_ai", "image_ai"], required=False)
            accounting_state = serializers.ChoiceField(choices=["pending", "estimated", "actual"], required=False)
            execution_state = serializers.ChoiceField(choices=["completed", "failed", "cancelled", "unknown"], required=False)
            since = serializers.DateTimeField(required=False)
            until = serializers.DateTimeField(required=False)
        query = Query(data=request.query_params)
        query.is_valid(raise_exception=True)
        fields = {"call_id": "pk", "account": "task__account_id", "since": "created_at__gte", "until": "created_at__lt"}
        calls = calls.filter(**{fields.get(k, k): v for k, v in query.validated_data.items()})
        page, pagination = calls_page(calls, request)
        return success_response(dict(items=[admin_call(call) for call in page], pagination=pagination))


class ProductionAdjustView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:production:adjust"

    @transaction.atomic
    def post(self, request, call_id):
        from .services import adjust

        class Input(serializers.Serializer):
            request_key = serializers.UUIDField()
            version = serializers.IntegerField(min_value=1)
            usage = UsageInput()
            reason = serializers.CharField(max_length=500)
            evidence = serializers.CharField(max_length=200)

        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        evidence = values.pop("evidence")
        values["reason"] = f"{values['reason']}（凭据 {evidence}）"
        if len(values["reason"]) > 500:
            raise serializers.ValidationError("原因及凭据合计不能超过 500 字符")
        call = adjust(call_id, **values)
        write_audit_log(request, action="production.usage.adjust", resource_type="production_call",
                        resource_id=str(call.pk), response_payload=admin_call(call))
        return success_response(admin_call(call))


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
        from .entitlements import filter_accounts

        class Query(serializers.Serializer):
            page = serializers.IntegerField(min_value=1, default=1)
            page_size = serializers.IntegerField(min_value=1, max_value=100, default=25)
            q = serializers.CharField(required=False, allow_blank=True, max_length=100)
            plan = serializers.ChoiceField(choices=["free", "pro", "unavailable"], required=False)

        query = Query(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        charged_accounts = ProductionLedger.objects.filter(delta_points__gt=0).values("call__task__account_id")
        users = get_user_model().objects.filter(is_active=True, pk__in=charged_accounts).order_by("-id")
        term = values.get("q", "").strip()
        if term:
            match = Q(username__icontains=term)
            if term.isdigit():
                match |= Q(pk=int(term))
            users = users.filter(match)
        now = timezone.now()
        if values.get("plan"):
            users = filter_accounts(users, values["plan"], now)
        paginator = Paginator(users, values["page_size"])
        page = paginator.get_page(values["page"])
        items = []
        for user in page:
            snapshot = quota(user, admin=True, now=now)
            items.append({
                "id": user.pk, "username": user.get_username(),
                "windows": snapshot["windows"], "pending_usage": snapshot["pending_usage"],
                "plan": snapshot["plan"], "membership_expires_at": snapshot["membership_expires_at"],
                "membership_verified_at": snapshot["membership_verified_at"],
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
            expected_plan = serializers.ChoiceField(choices=["free", "pro"])
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
                                          "windows": reset.windows, "plan": reset.plan})
        return success_response({"reset_id": reset.pk, "quota": quota(user, admin=True)})


class ProductionPricingPreviewView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:ai:production:publish"

    def post(self, request):
        from .services import points, PRECISION

        class Input(serializers.Serializer):
            rate = ModelRateInput()
            usage = UsageInput()
            size = serializers.CharField(max_length=32)

        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        rate, usage, size = (data.validated_data[key] for key in ("rate", "usage", "size"))
        if rate["mode"] == "images" and size not in rate["image_rates"]:
            raise serializers.ValidationError("图片规格未配置")
        charge = points(rate, usage, {"size": size})
        if charge is None:
            raise serializers.ValidationError("用量字段不完整或缓存 token 超出输入总量")
        return success_response({"points": str(charge.quantize(PRECISION, rounding=ROUND_HALF_UP))})


class ProductionAuditView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "menu:ai:production"

    def get(self, request):
        from backoffice.models import AdminAuditLog
        rows = AdminAuditLog.objects.filter(action__startswith="production.").select_related("user")
        page, pagination = calls_page(rows, request)
        return success_response({"items": [{
            "id": row.pk, "action": row.action, "resource_id": row.resource_id,
            "operator": row.user.get_username() if row.user else "",
            "created_at": row.created_at, "details": row.response_payload,
        } for row in page], "pagination": pagination})
