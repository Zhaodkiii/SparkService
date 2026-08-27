from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_config", "0004_exam_archive_updates"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiscenariomodelbinding",
            name="server_tool_scenarios",
            field=models.JSONField(
                blank=True,
                db_comment="场景模型绑定的 SparkService 服务端工具场景编码列表",
                default=list,
            ),
        ),
    ]
