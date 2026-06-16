from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MedicationReminderLocalAuthorization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(db_comment="是否启用本机提醒授权", db_index=True, default=True)),
                ("source", models.CharField(blank=True, db_comment="授权来源", default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_comment="创建时间", db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_comment="更新时间", db_index=True)),
                (
                    "medication_plan",
                    models.ForeignKey(
                        db_comment="具体服药计划 ID",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="local_authorizations",
                        to="medical.medicationplan",
                    ),
                ),
                (
                    "member",
                    models.ForeignKey(
                        db_comment="服药计划所属成员 ID",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="medication_reminder_local_authorizations",
                        to="medical.member",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        db_comment="接收本机提醒的登录用户 ID",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="medication_reminder_local_authorizations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "用药提醒本机授权",
                "verbose_name_plural": "用药提醒本机授权",
                "db_table": "medical_medication_reminder_local_authorization",
                "db_table_comment": "计划级本机提醒授权：当前用户是否同意为非本人计划创建本地提醒。",
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="medicationreminderlocalauthorization",
            constraint=models.UniqueConstraint(fields=("user", "medication_plan"), name="uniq_user_medication_plan_local_auth"),
        ),
        migrations.AddIndex(
            model_name="medicationreminderlocalauthorization",
            index=models.Index(fields=["user", "enabled"], name="medical_medi_user_id_8d2989_idx"),
        ),
        migrations.AddIndex(
            model_name="medicationreminderlocalauthorization",
            index=models.Index(fields=["member", "enabled"], name="medical_medi_member__42f678_idx"),
        ),
        migrations.AddIndex(
            model_name="medicationreminderlocalauthorization",
            index=models.Index(fields=["medication_plan", "enabled"], name="medical_medi_medicat_ec3767_idx"),
        ),
    ]
