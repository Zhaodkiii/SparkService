from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat_sync", "0002_chatthread_deleted_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatthread",
            name="image_delivery_mode",
            field=models.CharField(
                blank=True,
                choices=[("directMultimodal", "directMultimodal"), ("localOCR", "localOCR")],
                db_index=True,
                max_length=32,
                null=True,
            ),
        ),
    ]
