from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("task_system", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="task",
            name="notification_enabled",
            field=models.BooleanField(db_index=True, default=True, verbose_name="通知已开启"),
        ),
    ]
