from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0013_prescriptionbatch_batch_no_non_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicalcase",
            name="severity",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="medicalcase",
            name="case_status",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
