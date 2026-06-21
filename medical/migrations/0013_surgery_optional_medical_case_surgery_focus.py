from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0012_remove_membermedicalprofile_legacy_medication_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="membermedicalprofile",
            name="surgery_focus",
            field=models.JSONField(
                blank=True,
                db_comment="成员手术史摘要投影，由有效 Surgery 服务端重算",
                default=list,
            ),
        ),
        migrations.AlterField(
            model_name="surgery",
            name="medical_case",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="surgeries",
                to="medical.medicalcase",
            ),
        ),
    ]
