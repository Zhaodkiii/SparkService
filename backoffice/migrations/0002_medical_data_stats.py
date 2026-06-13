from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("backoffice", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MedicalDataGlobalStatsSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(default="global", max_length=32, unique=True)),
                ("users_with_medical_data", models.PositiveIntegerField(default=0)),
                ("users_with_ai_recognition", models.PositiveIntegerField(default=0)),
                ("medical_data_total", models.PositiveIntegerField(default=0)),
                ("attachment_total", models.PositiveIntegerField(default=0)),
                (
                    "refresh_status",
                    models.CharField(
                        choices=[("ready", "ready"), ("refreshing", "refreshing"), ("stale", "stale")],
                        default="ready",
                        max_length=16,
                    ),
                ),
                ("refreshed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "backoffice_medical_data_global_stats"},
        ),
        migrations.CreateModel(
            name="MedicalDataMemberStats",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("medical_case_count", models.PositiveIntegerField(default=0)),
                ("health_exam_report_count", models.PositiveIntegerField(default=0)),
                ("examination_report_count", models.PositiveIntegerField(default=0)),
                ("medicine_box_count", models.PositiveIntegerField(default=0)),
                ("prescription_count", models.PositiveIntegerField(default=0)),
                ("medication_plan_count", models.PositiveIntegerField(default=0)),
                ("symptom_count", models.PositiveIntegerField(default=0)),
                ("visit_count", models.PositiveIntegerField(default=0)),
                ("surgery_count", models.PositiveIntegerField(default=0)),
                ("follow_up_count", models.PositiveIntegerField(default=0)),
                ("attachment_count", models.PositiveIntegerField(default=0)),
                ("total_count", models.PositiveIntegerField(db_index=True, default=0)),
                ("ai_recognition_count", models.PositiveIntegerField(default=0)),
                ("ai_pending_count", models.PositiveIntegerField(default=0)),
                ("manual_source_count", models.PositiveIntegerField(default=0)),
                ("quality_flag_count", models.PositiveIntegerField(default=0)),
                ("today_medication_total", models.PositiveIntegerField(default=0)),
                ("today_medication_taken", models.PositiveIntegerField(default=0)),
                ("today_medication_skipped", models.PositiveIntegerField(default=0)),
                ("adherence_rate", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("last_medical_updated_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "refresh_status",
                    models.CharField(
                        choices=[("ready", "ready"), ("refreshing", "refreshing"), ("stale", "stale")],
                        db_index=True,
                        default="ready",
                        max_length=16,
                    ),
                ),
                ("refreshed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "member",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="admin_medical_stats",
                        to="medical.member",
                    ),
                ),
            ],
            options={
                "db_table": "backoffice_medical_data_member_stats",
                "indexes": [
                    models.Index(fields=["total_count", "last_medical_updated_at"], name="backoffice_m_total_c_a7d0d0_idx"),
                    models.Index(fields=["refresh_status", "refreshed_at"], name="backoffice_m_refresh_0e8f8f_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="MedicalDataUserStats",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("member_count", models.PositiveIntegerField(default=0)),
                ("members_with_data_count", models.PositiveIntegerField(db_index=True, default=0)),
                ("medical_data_total", models.PositiveIntegerField(db_index=True, default=0)),
                ("attachment_count", models.PositiveIntegerField(db_index=True, default=0)),
                ("ai_task_count", models.PositiveIntegerField(db_index=True, default=0)),
                ("quality_flag_count", models.PositiveIntegerField(default=0)),
                ("category_totals", models.JSONField(blank=True, default=dict)),
                ("last_medical_updated_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_source", models.CharField(blank=True, default="", max_length=32)),
                (
                    "refresh_status",
                    models.CharField(
                        choices=[("ready", "ready"), ("refreshing", "refreshing"), ("stale", "stale")],
                        db_index=True,
                        default="ready",
                        max_length=16,
                    ),
                ),
                ("refreshed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="medical_data_stats",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "backoffice_medical_data_user_stats",
                "indexes": [
                    models.Index(fields=["-last_medical_updated_at", "user_id"], name="backoffice_m_last_me_6d8a8a_idx"),
                    models.Index(fields=["-medical_data_total", "user_id"], name="backoffice_m_medical_8b9b9b_idx"),
                ],
            },
        ),
    ]
