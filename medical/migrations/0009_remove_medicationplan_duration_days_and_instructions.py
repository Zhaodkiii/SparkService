from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0008_medicinebox_dose_unit"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="medicationplan",
            name="duration_days",
        ),
    ]
