from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0003_rename_medical_medi_user_id_8d2989_idx_medical_med_user_id_9b40c2_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="medicationplan",
            name="dose_per_time",
            field=models.CharField(blank=True, db_comment="单次剂量文本", default="", max_length=64),
        ),
        migrations.AlterField(
            model_name="medicationplan",
            name="dose_unit",
            field=models.CharField(blank=True, db_comment="剂量单位", default="", max_length=32),
        ),
    ]
