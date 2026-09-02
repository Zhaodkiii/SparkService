import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("hospital_care", "0001_organization"),
        ("ai_config", "0006_alter_aiscenariomodelbinding_scenario_and_more"),
        ("chat_sync", "0017_drop_knowledge_index_tables"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClinicalAgentProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("public_summary", models.TextField(blank=True, default="")),
                ("greeting", models.TextField(blank=True, default="")),
                ("service_boundary", models.TextField(blank=True, default="")),
                (
                    "publication_status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("review", "Review"), ("published", "Published"), ("disabled", "Disabled")],
                        db_index=True,
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("doctor_editable_policy", models.JSONField(blank=True, default=dict)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("version", models.BigIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("department", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="clinical_agents", to="hospital_care.hospitaldepartment")),
                ("doctor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="clinical_agents", to="hospital_care.doctorprofile")),
                ("hospital", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="clinical_agents", to="hospital_care.hospital")),
                ("scenario_binding", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="clinical_agents", to="ai_config.aiscenariomodelbinding")),
            ],
        ),
        migrations.CreateModel(
            name="ClinicalAgentKnowledgeBinding",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("usage_scope", models.CharField(choices=[("hospital", "Hospital"), ("department", "Department"), ("doctor", "Doctor")], default="doctor", max_length=16)),
                ("sort_order", models.IntegerField(default=0)),
                ("status", models.CharField(choices=[("active", "Active"), ("disabled", "Disabled")], default="active", max_length=16)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="knowledge_bindings", to="hospital_care.clinicalagentprofile")),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="approved_clinical_knowledge_bindings", to=settings.AUTH_USER_MODEL)),
                ("knowledge_base", models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.PROTECT, related_name="clinical_agent_bindings", to="chat_sync.knowledgebase")),
            ],
        ),
        migrations.AddIndex(
            model_name="clinicalagentprofile",
            index=models.Index(fields=["hospital", "department", "publication_status"], name="idx_agent_hospital_dept_status"),
        ),
        migrations.AddConstraint(
            model_name="clinicalagentknowledgebinding",
            constraint=models.UniqueConstraint(fields=("agent", "knowledge_base"), name="uniq_agent_knowledge_base"),
        ),
    ]
