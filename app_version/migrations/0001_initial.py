# Generated manually for Spark app version control.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AppVersionConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("platform", models.CharField(choices=[("iOS", "iOS"), ("Android", "Android")], db_index=True, max_length=20)),
                ("bundle_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("channel", models.CharField(choices=[("production", "Production"), ("testflight", "TestFlight"), ("internal", "Internal")], db_index=True, default="production", max_length=32)),
                ("latest_version", models.CharField(max_length=50)),
                ("latest_build", models.CharField(blank=True, default="", max_length=50)),
                ("force_update_min_version", models.CharField(blank=True, default="", max_length=50)),
                ("force_update_min_build", models.CharField(blank=True, default="", max_length=50)),
                ("update_title", models.CharField(max_length=200)),
                ("update_message", models.TextField()),
                ("release_notes", models.TextField(blank=True, default="")),
                ("download_url", models.URLField(max_length=512)),
                ("enable_gradual_release", models.BooleanField(default=False)),
                ("gradual_release_percentage", models.PositiveSmallIntegerField(default=100)),
                ("gradual_release_min_version", models.CharField(blank=True, default="", max_length=50)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_app_version_configs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["platform", "bundle_id", "channel", "is_active"], name="app_version_platfor_be18ff_idx"),
                    models.Index(fields=["is_active", "created_at"], name="app_version_is_acti_bc2d08_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="VersionCheckLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("platform", models.CharField(db_index=True, max_length=20)),
                ("bundle_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("channel", models.CharField(blank=True, db_index=True, default="production", max_length=32)),
                ("current_version", models.CharField(max_length=50)),
                ("current_build", models.CharField(blank=True, default="", max_length=50)),
                ("device_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("system_version", models.CharField(blank=True, default="", max_length=50)),
                ("has_update", models.BooleanField(db_index=True, default=False)),
                ("force_update", models.BooleanField(db_index=True, default=False)),
                ("latest_version", models.CharField(blank=True, default="", max_length=50)),
                ("latest_build", models.CharField(blank=True, default="", max_length=50)),
                ("decision_reason", models.CharField(blank=True, default="", max_length=64)),
                ("ip_address", models.CharField(blank=True, default="", max_length=64)),
                ("request_id", models.CharField(blank=True, default="", max_length=64)),
                ("checked_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("config", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="check_logs", to="app_version.appversionconfig")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="version_check_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-checked_at", "-id"],
                "indexes": [
                    models.Index(fields=["platform", "checked_at"], name="app_version_platfor_6a708c_idx"),
                    models.Index(fields=["bundle_id", "device_id", "checked_at"], name="app_version_bundle__5301e3_idx"),
                    models.Index(fields=["has_update", "force_update"], name="app_version_has_upd_880e56_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="UpdateActionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("force_update_shown", "Force update shown"), ("optional_update_shown", "Optional update shown"), ("update_clicked", "Update clicked"), ("later_clicked", "Later clicked"), ("dismissed", "Dismissed")], db_index=True, max_length=50)),
                ("device_id", models.CharField(blank=True, default="", max_length=255)),
                ("platform", models.CharField(blank=True, default="", max_length=20)),
                ("request_id", models.CharField(blank=True, default="", max_length=64)),
                ("action_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("check_log", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="actions", to="app_version.versionchecklog")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="version_update_actions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-action_at", "-id"],
                "indexes": [
                    models.Index(fields=["action", "action_at"], name="app_version_action_44f7e0_idx"),
                    models.Index(fields=["user", "action_at"], name="app_version_user_id_be838f_idx"),
                ],
            },
        ),
    ]
