from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat_sync", "0008_chatthread_member_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatmessage",
            name="model_name",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]

