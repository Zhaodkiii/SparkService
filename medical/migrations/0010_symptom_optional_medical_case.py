from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0009_rename_med_mem_usr_mbr_rec_idx_medical_mem_user_id_403dae_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="symptom",
            name="medical_case",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="symptoms",
                to="medical.medicalcase",
            ),
        ),
    ]
