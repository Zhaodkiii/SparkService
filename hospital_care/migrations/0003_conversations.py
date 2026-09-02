import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("hospital_care", "0002_agent_profiles"),
        ("chat_sync", "0017_drop_knowledge_index_tables"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClinicalConversationBinding",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("thread", models.OneToOneField(db_constraint=False, on_delete=django.db.models.deletion.PROTECT, related_name="hospital_binding", to="chat_sync.chatthread")),
                ("service_status", models.CharField(choices=[("ai_active", "Ai Active"), ("pending_doctor", "Pending Doctor"), ("doctor_joined", "Doctor Joined"), ("ended", "Ended")], default="ai_active", max_length=32)),
                ("doctor_attention_level", models.CharField(choices=[("normal", "Normal"), ("follow_up", "Follow Up"), ("priority", "Priority")], default="normal", max_length=16)),
                ("attention_note", models.TextField(blank=True, default="")),
                ("risk_signal_level", models.CharField(choices=[("none", "None"), ("low", "Low"), ("medium", "Medium"), ("high", "High")], default="none", max_length=16)),
                ("assigned_at", models.DateTimeField(blank=True, null=True)),
                ("doctor_joined_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("end_reason", models.CharField(blank=True, default="", max_length=64)),
                ("version", models.BigIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="conversation_bindings", to="hospital_care.clinicalagentprofile")),
                ("department", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="conversation_bindings", to="hospital_care.hospitaldepartment")),
                ("doctor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="conversation_bindings", to="hospital_care.doctorprofile")),
                ("ended_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ended_hospital_conversations", to=settings.AUTH_USER_MODEL)),
                ("hospital", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="conversation_bindings", to="hospital_care.hospital")),
                ("risk_signal_message", models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="hospital_risk_bindings", to="chat_sync.chatmessage")),
            ],
        ),
        migrations.CreateModel(
            name="ChatMessageAttribution",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("message", models.OneToOneField(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, related_name="hospital_attribution", to="chat_sync.chatmessage")),
                ("actor_type", models.CharField(choices=[("patient", "Patient"), ("ai_agent", "Ai Agent"), ("doctor", "Doctor"), ("system", "System")], max_length=16)),
                ("display_name_snapshot", models.CharField(blank=True, default="", max_length=128)),
                ("source", models.CharField(choices=[("patient_app", "Patient App"), ("doctor_console", "Doctor Console"), ("ai_runtime", "Ai Runtime"), ("system", "System")], default="system", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="hospital_message_attributions", to=settings.AUTH_USER_MODEL)),
                ("agent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="message_attributions", to="hospital_care.clinicalagentprofile")),
                ("doctor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="message_attributions", to="hospital_care.doctorprofile")),
            ],
        ),
        migrations.CreateModel(
            name="HospitalCareCommandReceipt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("command_key", models.CharField(max_length=128)),
                ("request_hash", models.CharField(max_length=64)),
                ("resource_type", models.CharField(blank=True, default="", max_length=64)),
                ("resource_id", models.CharField(blank=True, default="", max_length=64)),
                ("response_code", models.IntegerField(default=0)),
                ("response_snapshot", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hospital_care_command_receipts", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="clinicalconversationbinding",
            index=models.Index(fields=["doctor", "service_status", "doctor_attention_level", "updated_at"], name="idx_conv_doctor_queue"),
        ),
        migrations.AddIndex(
            model_name="clinicalconversationbinding",
            index=models.Index(fields=["hospital", "department", "service_status"], name="idx_conv_hospital_dept_status"),
        ),
        migrations.AddConstraint(
            model_name="hospitalcarecommandreceipt",
            constraint=models.UniqueConstraint(fields=("actor_user", "command_key"), name="uniq_hospital_command_receipt"),
        ),
        migrations.AddIndex(
            model_name="hospitalcarecommandreceipt",
            index=models.Index(fields=["actor_user", "created_at"], name="idx_hospital_receipt_user_time"),
        ),
    ]
