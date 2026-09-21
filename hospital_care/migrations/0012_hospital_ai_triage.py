# Generated manually for AI triage conversation binding.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_config", "0006_alter_aiscenariomodelbinding_scenario_and_more"),
        ("chat_sync", "0001_initial"),
        ("hospital_care", "0011_consultation_allergy_history_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="HospitalAITriageBinding",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "hospital",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ai_triage_bindings",
                        to="hospital_care.hospital",
                    ),
                ),
                (
                    "scenario_binding",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="hospital_ai_triage_bindings",
                        to="ai_config.aiscenariomodelbinding",
                    ),
                ),
                (
                    "thread",
                    models.OneToOneField(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="hospital_ai_triage_binding",
                        to="chat_sync.chatthread",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["hospital", "updated_at"], name="idx_triage_hospital_updated"),
                ],
            },
        ),
    ]
