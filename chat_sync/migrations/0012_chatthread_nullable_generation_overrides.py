from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat_sync", "0011_chatmessageblock"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatthread",
            name="temperature",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="chatthread",
            name="max_tokens",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
