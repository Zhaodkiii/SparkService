from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat_sync", "0007_chatthread_sampling_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatthread",
            name="member_id",
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
    ]
