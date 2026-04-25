from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("ai_config", "0014_relax_scenario_binding_unique_add_identity"),
    ]

    operations = [
        migrations.CreateModel(
            name="SmallTask",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False, verbose_name="小任务ID")),
                ("name", models.CharField(max_length=100, verbose_name="小任务名称")),
                ("code", models.CharField(blank=True, help_text="格式：Local_数字 或 Service_数字", max_length=50, unique=True, verbose_name="唯一编码")),
                ("brief", models.CharField(blank=True, default="", max_length=255, verbose_name="小任务简介")),
                ("prompt", models.TextField(verbose_name="任务设定/Prompt")),
                ("icon", models.CharField(blank=True, default="", max_length=100, verbose_name="图标")),
                ("tool_list", models.JSONField(blank=True, default=list, verbose_name="调用工具列表")),
                ("source", models.CharField(choices=[("Local", "本地任务"), ("Service", "服务任务")], max_length=10, verbose_name="任务来源")),
                ("is_deleted", models.BooleanField(db_index=True, default=False, verbose_name="软删除状态")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
            ],
            options={
                "ordering": ["source", "id"],
                "db_table_comment": "AI小任务配置：本地/服务任务定义，按code与模型关联",
            },
        ),
        migrations.AddField(
            model_name="aimodelcatalog",
            name="related_task_codes",
            field=models.JSONField(blank=True, db_comment="关联小任务唯一编码列表", default=list),
        ),
        migrations.AddField(
            model_name="aiscenariomodelbinding",
            name="related_task_codes",
            field=models.JSONField(blank=True, db_comment="场景绑定关联小任务唯一编码列表", default=list),
        ),
        migrations.AddField(
            model_name="trialmodelpolicyitem",
            name="related_task_codes",
            field=models.JSONField(blank=True, db_comment="试用策略行关联小任务唯一编码列表", default=list),
        ),
    ]
