from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat_sync", "0003_chatrun_chatrunevent_chateventoutbox_and_more")]

    operations = [
        migrations.AddField("chatrun", "finish_reason", models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField("chatrun", "provider_request_id", models.CharField(blank=True, default="", max_length=128)),
        migrations.AddField("chateventoutbox", "lock_owner", models.CharField(blank=True, default="", max_length=128)),
        migrations.AddField("chateventoutbox", "locked_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("chatusagerecord", "usage_source", models.CharField(default="unavailable", max_length=16)),
    ]

