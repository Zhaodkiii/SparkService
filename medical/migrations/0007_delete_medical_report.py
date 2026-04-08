from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0006_followup_medication_medicationtakenrecord_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="MedicalReport",
        ),
    ]
