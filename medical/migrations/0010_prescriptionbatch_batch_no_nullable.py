# 空白 batch_no 存 NULL，避免 unique=True 与多行 "" 冲突导致 IntegrityError → 500。

from django.db import migrations, models


def normalize_empty_batch_no(apps, schema_editor):
    PrescriptionBatch = apps.get_model("medical", "PrescriptionBatch")
    PrescriptionBatch.objects.filter(batch_no="").update(batch_no=None)


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0009_rename_tables_medical_prefix"),
    ]

    operations = [
        migrations.AlterField(
            model_name="prescriptionbatch",
            name="batch_no",
            field=models.CharField(
                blank=True,
                db_comment="业务唯一批次号",
                default=None,
                help_text="业务批次号/处方号；未填时存库为 NULL，避免与 unique 冲突",
                max_length=128,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(normalize_empty_batch_no, migrations.RunPython.noop),
    ]
