from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("chat_sync", "0008_chat_websocket_ticket")]

    operations = [
        migrations.AddField(
            model_name="chatdeferredtoolstate",
            name="capability",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="chatdeferredtoolstate",
            name="capability_version",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="chatdeferredtoolstate",
            name="last_loaded_run",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="deferred_tool_loads", to="chat_sync.chatrun"),
        ),
        migrations.AddField(
            model_name="chatdeferredtoolstate",
            name="revoke_reason",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="chatdeferredtoolstate",
            name="schema_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="chatdeferredtoolstate",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
