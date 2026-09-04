from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status
from urllib import request as urllib_request
from urllib import error as urllib_error
import json

import logging

from ai_config.defaults import (
    DEFAULT_SCENARIOS,
)
from ai_config.models import (
    AIModelCatalog,
    AIProviderKeyConfig,
    AIScenarioModelBinding,
    IdentityKind,
    ScenarioKey,
    SmallTask,
    TrialApplication,
    TrialModelPolicy,
    TrialModelPolicyItem,
)
from ai_config.provider_resolution import (
    build_provider_index,
    load_active_api_providers,
    resolve_provider_for_model,
)
from ai_config.services import TrialService
from common.response import success_response, error_response
from hospital_care.models import ClinicalAgentProfile

logger = logging.getLogger(__name__)


def _bootstrap_json_string_list(value) -> list:
    """Bootstrap 下发给 iOS 的字符串数组：仅接受 JSON 列表，其它类型视为空。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if x is not None and str(x).strip() != ""]
    return []


def _bootstrap_trial_denial_message_and_status(trial: TrialApplication | None) -> tuple[str, str]:
    """非 Pro 时返回给客户端的说明文案与 trial_status。"""
    if trial is None:
        return "当前账号无试用记录，暂无 Pro 场景配置；请先在应用内申请试用。", TrialApplication.Status.NONE
    status = trial.status
    if status == TrialApplication.Status.ACTIVE and trial.is_active_trial():
        return "", status
    if status == TrialApplication.Status.EXPIRED:
        return "试用期已结束，无法拉取 Pro 场景配置；请续费或重新申请。", status
    if status == TrialApplication.Status.PENDING:
        return "试用申请审核中，暂无法使用 Pro 场景配置。", status
    if status == TrialApplication.Status.REJECTED:
        return "试用申请未通过，暂无 Pro 场景配置。", status
    if status == TrialApplication.Status.NONE:
        return "尚未开通 Pro 试用，暂无场景配置；请发起试用申请。", status
    return "当前账号不在有效 Pro 使用期内，暂无场景配置。", status


def _active_trial_policy_item_by_scenario_model() -> dict[tuple[str, int], TrialModelPolicyItem]:
    """当前启用的试用策略下，按 (scenario, model_id) 索引的策略行（用于覆盖绑定行上的展示字段）。"""
    policy_id = (
        TrialModelPolicy.objects.filter(is_active=True)
        .order_by("-updated_at")
        .values_list("pk", flat=True)
        .first()
    )
    if policy_id is None:
        return {}
    items = TrialModelPolicyItem.objects.filter(policy_id=policy_id, is_active=True).only(
        "scenario",
        "model_id",
        "system_provision",
        "brief_description",
        "ai_tool_scenarios",
        "related_task_codes",
    )
    return {(it.scenario, it.model_id): it for it in items}


def _bootstrap_small_task_payload(task: SmallTask) -> dict:
    return {
        "id": task.id,
        "name": task.name,
        "code": task.code,
        "brief": task.brief or "",
        "prompt": task.prompt or "",
        "icon": task.icon or "",
        "tool_list": _bootstrap_json_string_list(task.tool_list),
        "source": task.source,
    }


class AIBootstrapConfigView(APIView):
    """
    AI 配置 bootstrap 接口（仅返回场景模型配置）。

    改造后职责：
    - 只返回 `scenarios`（各场景下的 `models[]`），其他数据不再返回
    - 非 Pro 用户：返回空场景集合（客户端将回退到本地 bundle）
    - Pro 用户：返回完整的场景模型配置（含 endpoint、api_key 等）
    - 所有 Pro 模型标记 `source: "pro"`
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 判断是否为 Pro 用户
        is_pro = TrialService.is_pro_user(user=request.user)

        if not is_pro:
            trial_row = TrialApplication.objects.filter(user=request.user).first()
            trial_row = TrialService.ensure_status_fresh(trial=trial_row)
            trial_message, trial_status = _bootstrap_trial_denial_message_and_status(trial_row)
            revision = timezone.now().isoformat()
            payload = {
                "revision": revision,
                "scenarios": {},
                "smallTasks": [],
                "trial_status": trial_status,
                "trial_message": trial_message,
            }
            return success_response(payload, msg=trial_message, code=0)

        # Pro 用户：构建完整的场景模型配置
        provider_by_company = build_provider_index(load_active_api_providers())

        scenarios, related_task_codes = self._build_pro_scenarios(provider_by_company=provider_by_company)
        small_tasks = self._build_related_small_tasks(related_task_codes)

        revision = self._resolve_pro_revision()
        payload = {
            "revision": revision,
            "scenarios": scenarios,
            "smallTasks": small_tasks,
        }
        return success_response(payload, msg="ok", code=0)

    def _build_pro_scenarios(self, provider_by_company):
        """
        构建 Pro 用户的场景模型配置。

        返回格式与客户端 `AIScenarioRemoteBundle` 对齐：
        - `default_model`: 默认模型名
        - `models`: 模型列表，每个模型包含完整的 `AIScenarioRemoteModelRow` 字段
        - 所有模型标记 `source: "pro"`
        """
        payload = {}
        related_task_codes = set()
        trial_overlay = _active_trial_policy_item_by_scenario_model()

        # CHAT-000058：一次性形成医院医生智能体绑定排除集合。
        # 被任一 ClinicalAgentProfile.scenario_binding 引用的绑定不得进入通用 Pro bootstrap。
        hospital_agent_binding_ids = set(
            ClinicalAgentProfile.objects.filter(scenario_binding_id__isnull=False).values_list(
                "scenario_binding_id", flat=True
            )
        )

        for scenario_key in DEFAULT_SCENARIOS.keys():
            bindings = (
                AIScenarioModelBinding.objects.select_related("model")
                .filter(scenario=scenario_key, is_active=True)
                .exclude(id__in=hospital_agent_binding_ids)
                .order_by("position", "id")
            )

            if not bindings.exists():
                # 无绑定时返回空 bundle
                payload[scenario_key] = {
                    "default_model": "",
                    "models": [],
                }
                continue

            models_list = []
            default_model = None

            for row in bindings:
                model = row.model
                provider = resolve_provider_for_model(model.company, provider_by_company)
                is_agent = row.identity == IdentityKind.AGENT
                row_name = row.bootstrap_name()

                if row.is_default:
                    default_model = row_name

                policy_item = trial_overlay.get((scenario_key, model.pk))
                provision_src = policy_item if policy_item is not None else row
                task_codes = _bootstrap_json_string_list(getattr(provision_src, "related_task_codes", []))
                if not task_codes:
                    task_codes = _bootstrap_json_string_list(model.related_task_codes)
                related_task_codes.update(task_codes)

                # 构建符合 AIScenarioRemoteModelRow 格式的模型数据
                # 字段名需与 iOS `AIScenarioRemoteModelRow.CodingKeys` 一致：
                # - 多数能力字段为 snake_case（见 Swift 显式 rawValue）
                # - `systemProvision` / `briefDescription` / `aiScenarios` / `aiToolScenarios` 无 rawValue，JSON 须为 camelCase
                # - systemProvision / briefDescription / aiToolScenarios：优先当前启用试用策略的 TrialModelPolicyItem，否则 AIScenarioModelBinding
                model_data = {
                    "name": row_name,
                    "display_name": row.display_name or model.display_name or model.name,
                    "identity": row.identity,
                    "baseModelName": model.name if is_agent else None,
                    "company": model.company,
                    "endpoint": provider["endpoint"] if provider else "",
                    "api_key": provider["api_key"] if provider else "",
                    "supports_search": model.supports_search,
                    "supports_multimodal": model.supports_multimodal,
                    "supports_reasoning": model.supports_reasoning,
                    "supports_tool_use": model.supports_tool_use,
                    "supports_voice_gen": model.supports_voice_gen,
                    "supports_image_gen": model.supports_image_gen,
                    "supports_text": model.supports_text,
                    "supports_deep_reasoning": model.supports_reasoning,
                    "reasoning_controllable": model.reasoning_controllable,
                    "price_tier": model.price_tier,
                    "systemProvision": provision_src.system_provision or "",
                    "icon": model.icon or "",
                    "briefDescription": provision_src.brief_description or "",
                    "source": "pro",  # Pro 专属模型标记
                    "aiScenarios": [scenario_key],
                    "aiToolScenarios": _bootstrap_json_string_list(provision_src.ai_tool_scenarios),
                    "relatedTaskCodes": task_codes,
                    "is_default": bool(row.is_default),
                    "temperature": row.temperature,
                    "max_tokens": row.max_tokens,
                }
                models_list.append(model_data)

            # 如果没有默认模型，取第一个
            if default_model is None and models_list:
                default_model = models_list[0]["name"]
                models_list[0]["is_default"] = True

            payload[scenario_key] = {
                "default_model": default_model or "",
                "models": models_list,
            }

        return payload, related_task_codes

    def _build_related_small_tasks(self, related_task_codes: set[str]) -> list[dict]:
        # if not related_task_codes:
        #     return []
        rows = (
            SmallTask.objects.filter(
                source=SmallTask.Source.SERVICE,
                is_deleted=False,
                # code__in=related_task_codes,
            )
            .order_by("id")
        )
        return [_bootstrap_small_task_payload(row) for row in rows]

    def _resolve_pro_revision(self):
        """Pro 配置版本号：基于场景模型绑定和 Provider 配置的更新时间。"""
        points = [
            AIScenarioModelBinding.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            AIProviderKeyConfig.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            AIModelCatalog.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            TrialModelPolicyItem.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
            SmallTask.objects.order_by("-updated_at").values_list("updated_at", flat=True).first(),
        ]
        points = [point for point in points if point is not None]
        if not points:
            return timezone.now().isoformat()
        return max(points).isoformat()


class TrialStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        trial = TrialApplication.objects.filter(user=request.user).first()
        trial = TrialService.ensure_status_fresh(trial=trial)

        if trial is None:
            payload = {
                "status": TrialApplication.Status.NONE,
                "is_active": False,
                "grant_source": TrialApplication.GrantSource.AUTO,
                "started_at": None,
                "expires_at": None,
                "remaining_seconds": 0,
            }
            return success_response(payload, msg="ok", code=0)

        now = timezone.now()
        remaining_seconds = 0
        if trial.expires_at:
            remaining_seconds = max(int((trial.expires_at - now).total_seconds()), 0)
        payload = {
            "status": trial.status,
            "is_active": trial.is_active_trial(),
            "grant_source": trial.grant_source,
            "started_at": trial.started_at.isoformat() if trial.started_at else None,
            "expires_at": trial.expires_at.isoformat() if trial.expires_at else None,
            "remaining_seconds": remaining_seconds,
            "note": trial.note,
        }
        return success_response(payload, msg="ok", code=0)


class TrialApplyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        note = str(request.data.get("note", "") or "")
        request_id = getattr(request, "request_id", "") or ""
        try:
            req = TrialService.apply_trial(user=request.user, note=note, request_id=request_id)
            payload = {
                "submitted": True,
                "application_id": req.id,
                "sequence": req.sequence,
                "status": req.status,
                "message": "申请已提交，请等待通知",
            }
            return success_response(payload, msg="trial_submitted", code=0, status_code=status.HTTP_200_OK)
        except Exception as exc:  # noqa: BLE001 - unexpected infra/db errors should return stable schema
            logger.exception(
                "trial.apply.failed request_id=%s user_id=%s note=%s reason=%s",
                request_id,
                getattr(getattr(request, "user", None), "id", None),
                note,
                str(exc),
            )
            # Avoid HTTP 500 so client can show stable “system error” prompt.
            # Also keep `data` shape compatible with submission DTO to avoid client-side decode errors.
            return error_response(
                msg="trial_apply_failed",
                code=-1,
                status_code=status.HTTP_200_OK,
                data={
                    "submitted": False,
                    "application_id": 0,
                    "sequence": 0,
                    "status": "failed",
                    "message": "申请失败，请稍后重试",
                    "request_id": request_id,
                },
            )


class AIProviderConnectionTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_url = str(request.data.get("request_url", "") or "").strip()
        api_key = str(request.data.get("api_key", "") or "").strip()
        model = str(request.data.get("model", "") or "").strip() or "spark-chat-default"

        if not request_url:
            return success_response({"reachable": False, "message": "request_url_required"}, msg="ok", code=0)
        if not api_key:
            return success_response({"reachable": False, "message": "api_key_required"}, msg="ok", code=0)
        if request_url.startswith("http://") is False and request_url.startswith("https://") is False:
            return success_response({"reachable": False, "message": "invalid_request_url"}, msg="ok", code=0)

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 4,
            "temperature": 0,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            request_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            with urllib_request.urlopen(req, timeout=8) as response:
                ok = 200 <= int(response.status) < 300
                return success_response({"reachable": ok, "message": "ok" if ok else "http_error"}, msg="ok", code=0)
        except urllib_error.HTTPError as exc:
            return success_response({"reachable": False, "message": f"http_{exc.code}"}, msg="ok", code=0)
        except Exception:
            return success_response({"reachable": False, "message": "network_error"}, msg="ok", code=0)


class ScenarioToolPreviewView(APIView):
    """Preview scenario/model tool bindings. This is not a Run permission snapshot."""

    permission_classes = [IsAuthenticated]

    def get(self, request, scenario_key: str):
        key = str(scenario_key or "").strip()
        if key not in {item.value for item in ScenarioKey}:
            return error_response(msg="invalid_scenario", code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        from chat_sync.ai_runtime.tools.public_projector import public_display_name
        from chat_sync.ai_runtime.tools.registry import build_server_tool_registry
        from chat_sync.ai_runtime.tools.server_names import server_tool_name_values
        from chat_sync.ai_runtime.providers.factory import resolve_scenario_binding

        binding = resolve_scenario_binding(key)
        registry = build_server_tool_registry()
        server_names = server_tool_name_values()
        ai_tool_scenarios = list(getattr(binding, "ai_tool_scenarios", None) or []) if binding is not None else []
        server_tool_scenarios = list(getattr(binding, "server_tool_scenarios", None) or []) if binding is not None else []

        def _describe(name: str, *, server_field: bool) -> dict:
            entry = registry.get(name)
            registered = entry is not None
            requires_client = bool(entry and entry.policy.target == "client") or (
                not server_field and name not in server_names
            )
            return {
                "name": name,
                "display_name": public_display_name(name) if name in server_names else name,
                "version": entry.policy.version if entry else "",
                "registered": registered,
                "has_executor": registered and entry.tool is not None and entry.policy.target == "server",
                "requires_client_capability": requires_client,
            }

        tools = [_describe(str(name), server_field=True) for name in server_tool_scenarios if str(name).strip()]
        declared = [_describe(str(name), server_field=False) for name in ai_tool_scenarios if str(name).strip()]
        return success_response(
            {
                "scenario_key": key,
                "resolved_model": binding.model.name if binding is not None else "",
                "binding_id": binding.pk if binding is not None else None,
                "is_run_permission": False,
                "note": "This preview is the scenario/model binding declaration, not the current Run tool permission.",
                "ai_tool_scenarios": declared,
                "server_tool_scenarios": tools,
            },
            msg="ok",
        )
