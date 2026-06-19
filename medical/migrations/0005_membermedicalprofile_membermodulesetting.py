from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0004_medicationplan_optional_dose_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MemberMedicalProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_deleted", models.BooleanField(db_index=True, default=False, db_comment="是否删除")),
                ("deleted_at", models.DateTimeField(blank=True, db_comment="软删除时间", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, db_comment="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True, db_comment="更新时间")),
                ("chronic_conditions", models.JSONField(blank=True, db_comment="慢病档案标签列表，例如糖尿病、高血压、高血脂、痛风、脂肪肝、肾病", default=list)),
                ("long_term_medications", models.JSONField(blank=True, db_comment="长期用药名称或简称列表", default=list)),
                ("medication_notes", models.TextField(blank=True, db_comment="用药提醒或用药说明补充", default="")),
                ("exam_focus", models.JSONField(blank=True, db_comment="体检关注指标列表，例如血糖、血脂、尿酸、肝肾功能", default=list)),
                ("symptom_follow_up_focus", models.JSONField(blank=True, db_comment="症状与随访关注项列表", default=list)),
                ("notes", models.TextField(blank=True, db_comment="医疗模块补充说明", default="")),
                ("extra", models.JSONField(blank=True, db_comment="医疗档案扩展字段", default=dict)),
                ("member", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name="medical_profiles", to="medical.member")),
                ("user", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_items", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="MemberModuleSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_deleted", models.BooleanField(db_index=True, default=False, db_comment="是否删除")),
                ("deleted_at", models.DateTimeField(blank=True, db_comment="软删除时间", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, db_comment="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True, db_comment="更新时间")),
                ("module_code", models.CharField(choices=[("medical", "medical"), ("nutrition", "nutrition"), ("daily_health", "daily_health")], db_comment="模块编码，例如 medical、nutrition、daily_health", db_index=True, max_length=32)),
                ("is_enabled", models.BooleanField(db_index=True, default=True, db_comment="是否启用该模块")),
                ("is_completed", models.BooleanField(db_index=True, default=False, db_comment="该模块是否已完成首次维护")),
                ("display_order", models.PositiveSmallIntegerField(db_index=True, default=0, db_comment="首页模块排序序号")),
                ("summary_text", models.CharField(blank=True, db_comment="模块摘要文案，例如未设置、已完成体检关注项等", default="", max_length=255)),
                ("detail_data", models.JSONField(blank=True, db_comment="模块维护详情快照；用于后续回填与展示", default=dict)),
                ("completed_at", models.DateTimeField(blank=True, db_index=True, db_comment="模块首次完成时间", null=True)),
                ("extra", models.JSONField(blank=True, db_comment="模块配置扩展字段", default=dict)),
                ("member", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name="module_settings", to="medical.member")),
                ("user", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_items", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["display_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="membermedicalprofile",
            constraint=models.UniqueConstraint(fields=("user", "member"), name="uniq_member_medical_profile"),
        ),
        migrations.AddConstraint(
            model_name="membermodulesetting",
            constraint=models.UniqueConstraint(fields=("user", "member", "module_code"), name="uniq_member_module_setting"),
        ),
        migrations.AddIndex(
            model_name="membermedicalprofile",
            index=models.Index(fields=["user", "member"], name="medical_me_user_memb_1f2e34_idx"),
        ),
        migrations.AddIndex(
            model_name="membermodulesetting",
            index=models.Index(fields=["user", "member", "module_code"], name="medical_mem_user_memb_7a3c1b_idx"),
        ),
        migrations.AddIndex(
            model_name="membermodulesetting",
            index=models.Index(fields=["member", "is_enabled", "display_order"], name="medical_mem_member_0bf3dd_idx"),
        ),
    ]
