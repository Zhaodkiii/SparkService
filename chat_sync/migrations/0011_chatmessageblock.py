import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("chat_sync", "0010_remove_chatmessage_kind_content"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatMessageBlock",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(db_index=True, default="text", max_length=64)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("streaming", "Streaming"), ("ready", "Ready"), ("failed", "Failed")], default="ready", max_length=16)),
                ("revision", models.BigIntegerField(default=0)),
                ("order_key", models.FloatField(blank=True, null=True)),
                ("tool_call_id", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("parent_tool_call_id", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("parent_block_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("node_role", models.CharField(default="timeline", max_length=32)),
                ("anchor", models.JSONField(blank=True, null=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField()),
                ("updated_at", models.DateTimeField()),
                ("server_updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("message", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blocks", to="chat_sync.chatmessage")),
                ("thread", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="message_blocks", to="chat_sync.chatthread")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_message_blocks", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["order_key", "created_at", "id"],
                "indexes": [
                    models.Index(fields=["message", "order_key", "created_at"], name="idx_chat_block_msg_order"),
                    models.Index(fields=["user", "server_updated_at", "id"], name="idx_chat_block_user_sync"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "id"), name="uniq_chat_block_user_block_id"),
                ],
            },
        ),
    ]
