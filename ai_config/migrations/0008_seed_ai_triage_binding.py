from django.db import migrations


def seed_ai_triage_binding(apps, schema_editor):
    AIScenarioModelBinding = apps.get_model("ai_config", "AIScenarioModelBinding")
    if AIScenarioModelBinding.objects.filter(scenario="ai_triage", is_active=True).exists():
        return
    template = (
        AIScenarioModelBinding.objects.filter(scenario="chat", is_active=True)
        .order_by("-is_default", "position", "id")
        .first()
    )
    if template is None:
        return
    ai_tool_scenarios = list(template.ai_tool_scenarios or [])
    if "collect_symptoms" not in ai_tool_scenarios:
        ai_tool_scenarios.append("collect_symptoms")

    AIScenarioModelBinding.objects.create(
        scenario="ai_triage",
        identity=template.identity,
        model_id=template.model_id,
        display_name="AI 导诊",
        brief_description="根据症状辅助推荐科室与就医建议，不能替代医生诊断。",
        system_provision=template.system_provision
        or "你是医院 AI 导诊助手，根据用户描述的症状辅助推荐合适科室与就医建议，不能替代医生诊断。",
        is_active=True,
        is_default=True,
        position=template.position,
        temperature=template.temperature,
        max_tokens=template.max_tokens,
        # AI 导诊与普通对话共用客户端工具编排，仅通过当前场景模型行的
        # ai_tool_scenarios 控制可用工具，不在客户端硬编码导诊白名单。
        ai_tool_scenarios=ai_tool_scenarios,
        related_task_codes=template.related_task_codes,
        server_tool_scenarios=template.server_tool_scenarios,
    )


def unseed_ai_triage_binding(apps, schema_editor):
    AIScenarioModelBinding = apps.get_model("ai_config", "AIScenarioModelBinding")
    AIScenarioModelBinding.objects.filter(scenario="ai_triage").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("ai_config", "0007_scenario_ai_triage"),
    ]

    operations = [
        migrations.RunPython(seed_ai_triage_binding, unseed_ai_triage_binding),
    ]
