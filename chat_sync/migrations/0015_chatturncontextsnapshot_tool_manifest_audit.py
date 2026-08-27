from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat_sync", "0014_knowledge_center_rag"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatturncontextsnapshot",
            name="tool_manifest_filtered",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="chatturncontextsnapshot",
            name="tool_manifest_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="chatturncontextsnapshot",
            name="tool_manifest_source",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
