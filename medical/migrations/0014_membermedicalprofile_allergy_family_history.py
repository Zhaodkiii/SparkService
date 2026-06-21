from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0013_surgery_optional_medical_case_surgery_focus"),
    ]

    operations = [
        migrations.AddField(
            model_name="membermedicalprofile",
            name="allergies",
            field=models.JSONField(blank=True, db_comment="过敏源标签列表，例如青霉素、海鲜、花粉", default=list),
        ),
        migrations.AddField(
            model_name="membermedicalprofile",
            name="allergy_details",
            field=models.JSONField(
                blank=True,
                db_comment="过敏明细，键为过敏源名称，值含 category/severity/reactions/notes",
                default=dict,
            ),
        ),
        migrations.AddField(
            model_name="membermedicalprofile",
            name="allergy_history",
            field=models.TextField(blank=True, db_comment="过敏史补充说明", default=""),
        ),
        migrations.AddField(
            model_name="membermedicalprofile",
            name="family_history",
            field=models.JSONField(
                blank=True,
                db_comment="家族病史记录列表，每项含 disease/relative/category/diagnosed_age/notes",
                default=list,
            ),
        ),
    ]
