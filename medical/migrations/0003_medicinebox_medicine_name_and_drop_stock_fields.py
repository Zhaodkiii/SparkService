# Generated manually — merges drug_name + generic_name into medicine_name; drops remaining_quantity and unit.

from django.db import migrations, models


def _merged_medicine_name(generic: str, drug: str) -> str:
    g = (generic or "").strip()
    d = (drug or "").strip()
    if g and d:
        if g == d:
            return g
        return f"{g}（{d}）"
    return g or d


def forwards_merge_names(apps, schema_editor):
    MedicineBox = apps.get_model("medical", "MedicineBox")
    for row in MedicineBox.objects.all().iterator():
        merged = _merged_medicine_name(row.generic_name, row.drug_name)
        row.medicine_name = merged if merged else "未填写"
        row.save(update_fields=["medicine_name"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0002_medicinebox_type_and_generic_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicinebox",
            name="medicine_name",
            field=models.CharField(blank=True, default="", max_length=255, db_comment="药品名称（合并原通用名与商品名）"),
        ),
        migrations.RunPython(forwards_merge_names, noop_reverse),
        migrations.RemoveField(model_name="medicinebox", name="drug_name"),
        migrations.RemoveField(model_name="medicinebox", name="generic_name"),
        migrations.RemoveField(model_name="medicinebox", name="remaining_quantity"),
        migrations.RemoveField(model_name="medicinebox", name="unit"),
        migrations.AlterField(
            model_name="medicinebox",
            name="medicine_name",
            field=models.CharField(max_length=255, db_comment="药品名称（合并原通用名与商品名）"),
        ),
    ]
