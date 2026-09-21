from django.db import migrations


def enable_collect_symptoms_for_ai_triage(apps, schema_editor):
    AIScenarioModelBinding = apps.get_model("ai_config", "AIScenarioModelBinding")
    for binding in AIScenarioModelBinding.objects.filter(scenario="ai_triage", is_active=True).iterator():
        tool_names = list(binding.ai_tool_scenarios or [])
        if "collect_symptoms" in tool_names:
            continue
        tool_names.append("collect_symptoms")
        binding.ai_tool_scenarios = tool_names
        binding.save(update_fields=["ai_tool_scenarios"])


class Migration(migrations.Migration):

    dependencies = [
        ("ai_config", "0009_alter_aiscenariomodelbinding_scenario_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_collect_symptoms_for_ai_triage, migrations.RunPython.noop),
    ]
