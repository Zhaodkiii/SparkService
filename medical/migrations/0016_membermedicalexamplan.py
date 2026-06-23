from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("medical", "0015_membermedicalprofile_lifestyle_profiles"),
    ]

    operations = [
        migrations.CreateModel(
            name="MemberMedicalExamPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_deleted", models.BooleanField(db_comment="是否删除", db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, db_comment="软删除时间", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_comment="创建时间", db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_comment="更新时间", db_index=True)),
                (
                    "source",
                    models.CharField(
                        choices=[("ai_report", "ai_report"), ("ai_baseline", "ai_baseline"), ("manual", "manual")],
                        db_comment="来源：报告AI、基线AI、手动",
                        db_index=True,
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "draft"), ("confirmed", "confirmed"), ("archived", "archived")],
                        db_comment="计划状态",
                        db_index=True,
                        default="confirmed",
                        max_length=32,
                    ),
                ),
                ("title", models.CharField(db_comment="计划标题", max_length=128)),
                ("must_items", models.JSONField(blank=True, db_comment="必做体检项目", default=list)),
                ("recommended_items", models.JSONField(blank=True, db_comment="建议增加项目", default=list)),
                ("follow_up_items", models.JSONField(blank=True, db_comment="近期随访复查项目", default=list)),
                ("rationale", models.JSONField(blank=True, db_comment="生成依据说明", default=list)),
                ("risk_notice", models.TextField(blank=True, db_comment="医疗风险提示", default="")),
                (
                    "ai_trace_id",
                    models.CharField(blank=True, db_comment="AI 调用链路 ID", db_index=True, default="", max_length=64),
                ),
                ("prompt_version", models.CharField(blank=True, db_comment="Prompt 版本", default="", max_length=32)),
                ("model_name", models.CharField(blank=True, db_comment="实际使用模型", default="", max_length=128)),
                ("extra", models.JSONField(blank=True, db_comment="扩展信息", default=dict)),
                (
                    "member",
                    models.ForeignKey(
                        db_comment="所属成员",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="medical_exam_plans",
                        to="medical.member",
                    ),
                ),
                (
                    "source_report",
                    models.ForeignKey(
                        blank=True,
                        db_comment="来源体检报告",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="generated_exam_plans",
                        to="medical.healthexamreport",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "medical_member_exam_plan",
                "db_table_comment": "成员体检计划：AI 或手动生成的下一次体检/排查清单。",
                "ordering": ["-updated_at", "-id"],
                "indexes": [
                    models.Index(fields=["member", "status", "is_deleted"], name="medical_mem_status_del_idx"),
                    models.Index(fields=["member", "source", "is_deleted"], name="medical_mem_source_del_idx"),
                    models.Index(fields=["ai_trace_id"], name="medical_exam_plan_trace_idx"),
                ],
            },
        ),
    ]
