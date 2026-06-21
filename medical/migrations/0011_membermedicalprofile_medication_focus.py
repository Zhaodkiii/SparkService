from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0010_symptom_optional_medical_case"),
    ]

    operations = [
        migrations.AddField(
            model_name="membermedicalprofile",
            name="medication_focus",
            field=models.JSONField(
                blank=True,
                db_comment="成员长期用药摘要投影，由有效 MedicationPlan 服务端重算",
                default=list,
            ),
        ),
    ]
