from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("chat_sync", "0009_chatmessage_model_name"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="chatmessage",
            name="content",
        ),
        migrations.RemoveField(
            model_name="chatmessage",
            name="kind",
        ),
    ]
