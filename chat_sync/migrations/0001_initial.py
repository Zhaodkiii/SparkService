from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatThread",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("patient_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("title", models.CharField(default="New Chat", max_length=255)),
                ("scenario", models.CharField(choices=[("chat", "Chat")], default="chat", max_length=32)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("server_updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_threads", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "id"), name="uniq_chat_thread_user_thread"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("role", models.CharField(choices=[("system", "System"), ("user", "User"), ("assistant", "Assistant")], max_length=16)),
                ("kind", models.CharField(choices=[("text", "Text"), ("tool", "Tool"), ("card", "Card"), ("system", "System")], default="text", max_length=16)),
                ("content", models.TextField(blank=True, default="")),
                ("client_message_id", models.UUIDField(db_index=True)),
                ("server_message_id", models.CharField(db_index=True, max_length=64)),
                ("delivery_state", models.CharField(choices=[("pending", "Pending"), ("sending", "Sending"), ("sent", "Sent"), ("failed", "Failed"), ("read", "Read")], default="sent", max_length=16)),
                ("tombstone", models.BooleanField(db_index=True, default=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(db_index=True)),
                ("server_updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "thread",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="chat_sync.chatthread"),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_messages", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(fields=["user", "server_updated_at", "id"], name="idx_chat_msg_user_sync"),
                    models.Index(fields=["thread", "created_at", "id"], name="idx_chat_msg_thread_created"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "client_message_id"), name="uniq_chat_message_user_client_id"),
                    models.UniqueConstraint(fields=("user", "server_message_id"), name="uniq_chat_message_user_server_id"),
                ],
            },
        ),
    ]
