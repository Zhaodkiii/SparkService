from django.db import migrations, models


def backfill_binding_display_name(apps, schema_editor):
    binding_model = apps.get_model("ai_config", "AIScenarioModelBinding")
    for row in binding_model.objects.select_related("model").iterator():
        if row.display_name:
            continue
        row.display_name = row.model.display_name
        row.save(update_fields=["display_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("ai_config", "0002_remove_scenario_model_identity_unique_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiscenariomodelbinding",
            name="display_name",
            field=models.CharField(
                blank=True,
                db_comment="场景内展示名称；agent可配置业务名称如报告解读助手",
                default="",
                max_length=128,
            ),
        ),
        migrations.RunPython(backfill_binding_display_name, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="aiscenariomodelbinding",
            name="display_name",
            field=models.CharField(
                db_comment="场景内展示名称；agent可配置业务名称如报告解读助手",
                max_length=128,
            ),
        ),
    ]
