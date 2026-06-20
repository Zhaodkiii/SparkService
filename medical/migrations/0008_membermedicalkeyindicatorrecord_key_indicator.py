from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0007_med_exam_detail_db_comments"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MemberMedicalKeyIndicatorRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_deleted", models.BooleanField(db_index=True, default=False, db_comment="是否删除")),
                ("deleted_at", models.DateTimeField(blank=True, db_comment="软删除时间", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, db_comment="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True, db_comment="更新时间")),
                ("source", models.CharField(choices=[("guide_qa", "guide_qa"), ("manual", "manual"), ("ai_follow_up", "ai_follow_up"), ("report_extraction", "report_extraction"), ("device", "device")], db_comment="记录来源：问答引导、手动录入、AI随访、报告抽取、设备", db_index=True, max_length=32)),
                ("scenario", models.CharField(choices=[("medical_guide", "medical_guide"), ("follow_up", "follow_up"), ("risk_assessment", "risk_assessment"), ("exam_plan", "exam_plan")], db_comment="业务场景：医疗引导、随访、风险评估、体检计划", db_index=True, max_length=32)),
                ("recorded_at", models.DateTimeField(blank=True, db_comment="用户填写或测量时间", db_index=True, null=True)),
                ("qa_session_id", models.CharField(blank=True, db_comment="问答流程会话 ID，用于回溯本次引导", db_index=True, default="", max_length=64)),
                ("title", models.CharField(blank=True, db_comment="记录标题，例如医疗引导关键指标", default="", max_length=128)),
                ("summary", models.TextField(blank=True, db_comment="记录摘要，例如血压偏高、尿酸偏高", default="")),
                ("extra", models.JSONField(blank=True, db_comment="扩展信息，例如原始问答、AI解释、设备来源", default=dict)),
                ("member", models.ForeignKey(db_comment="所属成员", db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name="key_indicator_records", to="medical.member")),
                ("user", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_items", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "medical_member_key_indicator_record",
                "db_table_comment": "成员关键健康指标记录主表，一次问答/随访/手动录入可关联多条指标明细。",
                "ordering": ["-recorded_at", "-updated_at", "-id"],
            },
        ),
        migrations.AlterField(
            model_name="medexamdetail",
            name="business_type",
            field=models.CharField(choices=[("health_exam_report", "health_exam_report"), ("examination_report", "examination_report"), ("key_indicator", "key_indicator")], db_comment="业务类型：health_exam_report（体检报告）或 examination_report（检查/检验报告）", db_index=True, max_length=32),
        ),
        migrations.AddIndex(
            model_name="membermedicalkeyindicatorrecord",
            index=models.Index(fields=["user", "member", "recorded_at"], name="med_mem_usr_mbr_rec_idx"),
        ),
        migrations.AddIndex(
            model_name="membermedicalkeyindicatorrecord",
            index=models.Index(fields=["member", "source", "recorded_at"], name="med_mem_mbr_src_rec_idx"),
        ),
        migrations.AddIndex(
            model_name="membermedicalkeyindicatorrecord",
            index=models.Index(fields=["member", "scenario", "recorded_at"], name="med_mem_mbr_scn_rec_idx"),
        ),
        migrations.AddIndex(
            model_name="membermedicalkeyindicatorrecord",
            index=models.Index(fields=["qa_session_id"], name="med_mem_qa_session_idx"),
        ),
    ]
