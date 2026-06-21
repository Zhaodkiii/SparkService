from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0014_membermedicalprofile_allergy_family_history"),
    ]

    operations = [
        migrations.AddField(
            model_name="membermedicalprofile",
            name="smoking_profile",
            field=models.JSONField(
                blank=True,
                db_comment="吸烟档案：status/count/history_duration/quit_duration",
                default=dict,
            ),
        ),
        migrations.AddField(
            model_name="membermedicalprofile",
            name="drinking_profile",
            field=models.JSONField(
                blank=True,
                db_comment="饮酒档案：status/count/history_duration/quit_duration/types",
                default=dict,
            ),
        ),
        migrations.AddField(
            model_name="membermedicalprofile",
            name="exercise_profile",
            field=models.JSONField(
                blank=True,
                db_comment="运动档案：frequency/intensity/types/duration_minutes",
                default=dict,
            ),
        ),
        migrations.AddField(
            model_name="membermedicalprofile",
            name="sleep_hours",
            field=models.FloatField(blank=True, db_comment="平均睡眠时长（小时）", null=True),
        ),
    ]
