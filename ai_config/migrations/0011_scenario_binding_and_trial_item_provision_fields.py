# Generated manually for Pro bootstrap field relocation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_config", "0010_alter_aimodelcatalog_table_comment_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="aimodelcatalog",
            name="ai_tool_scenarios",
        ),
        migrations.RemoveField(
            model_name="aimodelcatalog",
            name="brief_description",
        ),
        migrations.RemoveField(
            model_name="aimodelcatalog",
            name="system_provision",
        ),
        migrations.AddField(
            model_name="aiscenariomodelbinding",
            name="ai_tool_scenarios",
            field=models.JSONField(
                blank=True,
                db_comment="场景绑定aiToolScenarios_JSON_bootstrap优先试用策略行覆盖",
                default=list,
            ),
        ),
        migrations.AddField(
            model_name="aiscenariomodelbinding",
            name="brief_description",
            field=models.TextField(
                blank=True,
                db_comment="场景绑定briefDescription_bootstrap优先试用策略行覆盖",
                default="",
            ),
        ),
        migrations.AddField(
            model_name="aiscenariomodelbinding",
            name="system_provision",
            field=models.TextField(
                blank=True,
                db_comment="场景绑定systemProvision_bootstrap优先试用策略行覆盖",
                default="",
            ),
        ),
        migrations.AddField(
            model_name="trialmodelpolicyitem",
            name="ai_tool_scenarios",
            field=models.JSONField(
                blank=True,
                db_comment="试用策略行aiToolScenarios_JSON_bootstrap覆盖场景绑定",
                default=list,
            ),
        ),
        migrations.AddField(
            model_name="trialmodelpolicyitem",
            name="brief_description",
            field=models.TextField(
                blank=True,
                db_comment="试用策略行briefDescription_bootstrap覆盖场景绑定",
                default="",
            ),
        ),
        migrations.AddField(
            model_name="trialmodelpolicyitem",
            name="system_provision",
            field=models.TextField(
                blank=True,
                db_comment="试用策略行systemProvision_bootstrap覆盖场景绑定",
                default="",
            ),
        ),
    ]
