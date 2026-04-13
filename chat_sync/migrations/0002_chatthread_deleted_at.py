from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat_sync", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatthread",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
