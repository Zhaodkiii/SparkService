import hashlib
import json
import uuid

from django.db import migrations, models


def backfill_interaction_identity(apps, schema_editor):
    Interaction = apps.get_model("chat_sync", "ChatPendingInteraction")
    for row in Interaction.objects.all().iterator():
        payload = row.request_schema or {}
        request_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        row.public_id = uuid.uuid4()
        row.interaction_key = f"run:{row.run_id}:tool:{row.tool_call_id}:stage:0"
        row.request_hash = request_hash
        row.save(update_fields=["public_id", "interaction_key", "request_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("chat_sync", "0006_chattoolcall_arguments_hash_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="public_id",
            field=models.UUIDField(db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="schema_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="interaction_key",
            field=models.CharField(db_index=True, max_length=192, null=True),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="request_hash",
            field=models.CharField(default="", max_length=64),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="required_platform",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="required_capability",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="tool_version",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="claimed_by_device",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="claim_token_hash",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="claim_expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="max_attempts",
            field=models.PositiveIntegerField(default=3),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="response_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="result_summary",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="result_ref",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="last_error_code",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="chatpendinginteraction",
            name="response_received_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_interaction_identity, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="chatpendinginteraction",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="chatpendinginteraction",
            name="interaction_key",
            field=models.CharField(db_index=True, default="", max_length=192, unique=True),
        ),
        migrations.AlterField(
            model_name="chatpendinginteraction",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("claimed", "Claimed"),
                    ("resolved", "Resolved"),
                    ("refused", "Refused"),
                    ("expired", "Expired"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddIndex(
            model_name="chatpendinginteraction",
            index=models.Index(fields=["status", "claim_expires_at"], name="idx_ai_interaction_claim"),
        ),
        migrations.AddIndex(
            model_name="chatpendinginteraction",
            index=models.Index(fields=["required_platform", "status"], name="idx_ai_interaction_platform"),
        ),
    ]
