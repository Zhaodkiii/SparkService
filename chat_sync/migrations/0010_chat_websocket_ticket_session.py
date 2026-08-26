from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat_sync", "0009_chat_capability_deferred_tool_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatwebsocketticket",
            name="web_session_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="chatwebsocketticket",
            name="web_session_version",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
