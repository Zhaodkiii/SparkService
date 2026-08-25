import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("chat_sync", "0007_chat_pending_interaction_control"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatWebSocketTicket",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("websocket_path", models.CharField(default="/ws/chat/runs/", max_length=128)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_ws_tickets", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "chat_sync_ai_ws_ticket"},
        ),
        migrations.AddIndex(
            model_name="chatwebsocketticket",
            index=models.Index(fields=["expires_at", "used_at"], name="idx_ai_ws_ticket_expiry"),
        ),
    ]
