from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("chat_sync", "0004_p2_provider_execution_fields")]

    operations = [
        migrations.AddField(
            model_name="chatthreadpreferences",
            name="active_head_message",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ai_active_preference_heads",
                to="chat_sync.chatmessage",
            ),
        ),
        migrations.AddField(
            model_name="chatrun",
            name="context_parent_message",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ai_context_child_runs",
                to="chat_sync.chatmessage",
            ),
        ),
        migrations.AddField("chatturncontextsnapshot", "schema_version", models.PositiveSmallIntegerField(default=1)),
        migrations.AddField("chatturncontextsnapshot", "prompt_version", models.CharField(default="chat.prompt.v1", max_length=64)),
        migrations.AddField("chatturncontextsnapshot", "language", models.CharField(blank=True, default="zh-CN", max_length=32)),
        migrations.AddField("chatturncontextsnapshot", "history_head_message_id", models.BigIntegerField(blank=True, null=True)),
        migrations.AddField("chatturncontextsnapshot", "selected_message_ids", models.JSONField(blank=True, default=list)),
        migrations.AddField("chatturncontextsnapshot", "history_summary", models.TextField(blank=True, default="")),
        migrations.AddField("chatturncontextsnapshot", "summary_up_to_message_id", models.BigIntegerField(blank=True, null=True)),
        migrations.AddField("chatturncontextsnapshot", "route_snapshot", models.JSONField(blank=True, default=dict)),
        migrations.AddField("chatturncontextsnapshot", "build_status", models.CharField(default="ready", max_length=16)),
        migrations.AddField("chatturncontextsnapshot", "built_at", models.DateTimeField(blank=True, null=True)),
    ]
