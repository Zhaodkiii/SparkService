from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0007_delete_medical_report"),
    ]

    operations = [
        migrations.AlterField(
            model_name="examinationreport",
            name="organization_name",
            field=models.CharField(blank=True, default="", max_length=255, null=True),
        ),
    ]
