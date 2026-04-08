from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0010_prescriptionbatch_batch_no_nullable"),
    ]

    operations = [
        migrations.AlterField(
            model_name="healthexamreport",
            name="institution_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
