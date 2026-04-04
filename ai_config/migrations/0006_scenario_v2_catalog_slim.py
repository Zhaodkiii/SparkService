from django.db import migrations, models


def forwards_rename_scenarios(apps, schema_editor):
    AIScenarioConfig = apps.get_model("ai_config", "AIScenarioConfig")
    TrialModelPolicyItem = apps.get_model("ai_config", "TrialModelPolicyItem")
    mapping = {
        "medical_extraction": "optimization_text",
        "embedding": "model_config",
    }
    for old, new in mapping.items():
        AIScenarioConfig.objects.filter(scenario=old).update(scenario=new)
        TrialModelPolicyItem.objects.filter(scenario=old).update(scenario=new)


def backwards_rename_scenarios(apps, schema_editor):
    AIScenarioConfig = apps.get_model("ai_config", "AIScenarioConfig")
    TrialModelPolicyItem = apps.get_model("ai_config", "TrialModelPolicyItem")
    mapping = {
        "optimization_text": "medical_extraction",
        "model_config": "embedding",
    }
    for new, old in mapping.items():
        AIScenarioConfig.objects.filter(scenario=new).update(scenario=old)
        TrialModelPolicyItem.objects.filter(scenario=new).update(scenario=old)


def forwards_price_tier(apps, schema_editor):
    AIModelCatalog = apps.get_model("ai_config", "AIModelCatalog")
    for row in AIModelCatalog.objects.all():
        tier = 1 if getattr(row, "supports_pricing", False) else 0
        row.price_tier = tier
        row.save(update_fields=["price_tier"])


def backwards_price_tier(apps, schema_editor):
    AIModelCatalog = apps.get_model("ai_config", "AIModelCatalog")
    for row in AIModelCatalog.objects.all():
        row.supports_pricing = row.price_tier > 0
        row.save(update_fields=["supports_pricing"])


class Migration(migrations.Migration):
    dependencies = [
        ("ai_config", "0005_scenario_trial_model_fk_refactor"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiscenarioconfig",
            name="identity",
            field=models.CharField(
                choices=[("model", "Model"), ("agent", "Agent")],
                default="model",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="aimodelcatalog",
            name="price_tier",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(forwards_price_tier, backwards_price_tier),
        migrations.RunPython(forwards_rename_scenarios, backwards_rename_scenarios),
        migrations.RemoveField(
            model_name="aimodelcatalog",
            name="supports_pricing",
        ),
        migrations.RemoveField(
            model_name="aimodelcatalog",
            name="identity",
        ),
        migrations.RemoveField(
            model_name="aimodelcatalog",
            name="usage_scenario",
        ),
        migrations.AlterField(
            model_name="aiscenarioconfig",
            name="scenario",
            field=models.CharField(
                choices=[
                    ("chat", "Chat"),
                    ("optimization_text", "Optimization Text"),
                    ("optimization_visual", "Optimization Visual"),
                    ("context_folding", "Context Folding"),
                    ("router", "Router"),
                    ("model_config", "Model Config"),
                    ("report_interpretation", "Report Interpretation"),
                ],
                max_length=64,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="trialmodelpolicyitem",
            name="scenario",
            field=models.CharField(
                choices=[
                    ("chat", "Chat"),
                    ("optimization_text", "Optimization Text"),
                    ("optimization_visual", "Optimization Visual"),
                    ("context_folding", "Context Folding"),
                    ("router", "Router"),
                    ("model_config", "Model Config"),
                    ("report_interpretation", "Report Interpretation"),
                ],
                max_length=64,
            ),
        ),
        migrations.AddConstraint(
            model_name="aimodelcatalog",
            constraint=models.CheckConstraint(
                condition=models.Q(price_tier__gte=0) & models.Q(price_tier__lte=3),
                name="aimodelcatalog_price_tier_0_3",
            ),
        ),
    ]
