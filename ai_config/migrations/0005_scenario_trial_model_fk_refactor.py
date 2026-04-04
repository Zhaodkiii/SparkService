import django.db.models.deletion
from django.db import migrations, models


def _ensure_model(catalog_model, model_name: str):
    row = catalog_model.objects.filter(name=model_name).first()
    if row:
        return row
    return catalog_model.objects.create(
        name=model_name,
        display_name=model_name,
        company="UNKNOWN",
        source="system",
    )


def forwards_copy_model_fk(apps, schema_editor):
    AIModelCatalog = apps.get_model("ai_config", "AIModelCatalog")
    AIScenarioConfig = apps.get_model("ai_config", "AIScenarioConfig")
    TrialModelPolicyItem = apps.get_model("ai_config", "TrialModelPolicyItem")

    for row in AIScenarioConfig.objects.all():
        model_name = (row.model or "").strip()
        if not model_name:
            continue
        model_row = _ensure_model(AIModelCatalog, model_name)
        row.model_ref_id = model_row.id
        row.save(update_fields=["model_ref"])

    for row in TrialModelPolicyItem.objects.all():
        model_name = (row.model or "").strip()
        if not model_name:
            continue
        model_row = _ensure_model(AIModelCatalog, model_name)
        row.model_ref_id = model_row.id
        row.save(update_fields=["model_ref"])


def backwards_copy_model_name(apps, schema_editor):
    AIScenarioConfig = apps.get_model("ai_config", "AIScenarioConfig")
    TrialModelPolicyItem = apps.get_model("ai_config", "TrialModelPolicyItem")

    for row in AIScenarioConfig.objects.select_related("model_ref").all():
        row.model = row.model_ref.name if row.model_ref else ""
        row.save(update_fields=["model"])

    for row in TrialModelPolicyItem.objects.select_related("model_ref").all():
        row.model = row.model_ref.name if row.model_ref else ""
        row.save(update_fields=["model"])


class Migration(migrations.Migration):
    dependencies = [
        ("ai_config", "0004_aimodelcatalog_usage_and_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiscenarioconfig",
            name="model_ref",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="scenario_configs_tmp",
                to="ai_config.aimodelcatalog",
            ),
        ),
        migrations.AddField(
            model_name="trialmodelpolicyitem",
            name="model_ref",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="trial_policy_items_tmp",
                to="ai_config.aimodelcatalog",
            ),
        ),
        migrations.RunPython(forwards_copy_model_fk, backwards_copy_model_name),
        migrations.RemoveField(model_name="aiscenarioconfig", name="api_key"),
        migrations.RemoveField(model_name="aiscenarioconfig", name="endpoint"),
        migrations.RemoveField(model_name="trialmodelpolicyitem", name="api_key"),
        migrations.RemoveField(model_name="trialmodelpolicyitem", name="endpoint"),
        migrations.RemoveField(model_name="aiscenarioconfig", name="model"),
        migrations.RemoveField(model_name="trialmodelpolicyitem", name="model"),
        migrations.RenameField(model_name="aiscenarioconfig", old_name="model_ref", new_name="model"),
        migrations.RenameField(model_name="trialmodelpolicyitem", old_name="model_ref", new_name="model"),
        migrations.AlterField(
            model_name="aiscenarioconfig",
            name="model",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="scenario_configs",
                to="ai_config.aimodelcatalog",
            ),
        ),
        migrations.AlterField(
            model_name="trialmodelpolicyitem",
            name="model",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="trial_policy_items",
                to="ai_config.aimodelcatalog",
            ),
        ),
        migrations.AlterModelOptions(
            name="trialmodelpolicyitem",
            options={"ordering": ["position", "scenario", "model__name"]},
        ),
    ]
