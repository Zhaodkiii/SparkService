from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat_sync", "0004_alter_chatthread_image_delivery_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatthread",
            name="current_model_name",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
