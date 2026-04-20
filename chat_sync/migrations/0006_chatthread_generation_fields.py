from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat_sync", "0005_chatthread_current_model_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatthread",
            name="max_tokens",
            field=models.IntegerField(default=4096),
        ),
        migrations.AddField(
            model_name="chatthread",
            name="role_prompt",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="chatthread",
            name="temperature",
            field=models.FloatField(default=0.6),
        ),
    ]
