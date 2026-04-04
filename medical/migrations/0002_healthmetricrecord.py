from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HealthMetricRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("client_uid", models.UUIDField(db_index=True, default=uuid.uuid4)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("profile_client_uid", models.UUIDField(db_index=True)),
                ("metric_type", models.CharField(db_index=True, max_length=64)),
                ("value", models.FloatField(default=0)),
                ("unit", models.CharField(default="", max_length=32)),
                ("recorded_at", models.DateTimeField(db_index=True)),
                ("note", models.TextField(blank=True, default="")),
                (
                    "user",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="healthmetricrecord_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-recorded_at", "-updated_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="healthmetricrecord",
            constraint=models.UniqueConstraint(fields=("user", "client_uid"), name="uniq_health_metric_user_client_uid"),
        ),
    ]
