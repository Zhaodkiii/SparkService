from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0005_alter_medicinebox_total_quantity_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicationplan",
            name="every_n_days",
            field=models.PositiveSmallIntegerField(
                blank=True,
                db_comment="间隔天数（仅每几天模式生效）",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="medicationplan",
            name="frequency_type",
            field=models.CharField(
                choices=[
                    ("daily", "每天"),
                    ("every_n_days", "每几天"),
                    ("weekly", "每周指定星期"),
                ],
                db_comment="频次类型：每天/每几天/每周",
                default="daily",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="medicationplan",
            name="weekly_weekdays",
            field=models.JSONField(
                blank=True,
                db_comment="每周服药星期 [1,2,3,6,7]，1=周一…7=周日",
                default=list,
            ),
        ),
        migrations.RemoveField(
            model_name="medicationplan",
            name="frequency_code",
        ),
    ]
