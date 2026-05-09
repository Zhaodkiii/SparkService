from django.db import migrations, models


_LEGACY_MEDICINE_TYPES = frozenset(
    {
        "western",
        "chinese_patent",
        "tcm_decoction",
        "supplement",
        "external",
        "device",
        "other",
    }
)


def forwards_medicine_box(apps, schema_editor):
    MedicineBox = apps.get_model("medical", "MedicineBox")
    for row in MedicineBox.objects.filter(generic_name="").exclude(drug_name=""):
        row.generic_name = row.drug_name
        row.save(update_fields=["generic_name"])
    MedicineBox.objects.filter(generic_name="", drug_name="").update(generic_name="未填写")
    MedicineBox.objects.filter(medicine_type__in=_LEGACY_MEDICINE_TYPES).update(medicine_type="uncategorized")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards_medicine_box, noop_reverse),
        migrations.AlterField(
            model_name="medicinebox",
            name="drug_name",
            field=models.CharField(
                blank=True,
                db_comment="药品名称",
                default="",
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="medicinebox",
            name="generic_name",
            field=models.CharField(db_comment="通用名", max_length=255),
        ),
        migrations.AlterField(
            model_name="medicinebox",
            name="medicine_type",
            field=models.CharField(
                blank=True,
                db_comment="药品类型（预设编码、中文选项值或自定义文案，可空）",
                db_index=True,
                max_length=128,
                null=True,
            ),
        ),
    ]
