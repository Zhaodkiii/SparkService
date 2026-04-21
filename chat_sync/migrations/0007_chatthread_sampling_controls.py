from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat_sync", "0006_chatthread_generation_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatthread",
            name="top_p",
            field=models.FloatField(default=1.0),
        ),
        migrations.AddField(
            model_name="chatthread",
            name="max_messages",
            field=models.IntegerField(default=20),
        ),
    ]
