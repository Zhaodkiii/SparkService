from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def preserve_print_receipt_dates(apps, schema_editor):
    task = apps.get_model("ai_production", "ProductionTask")
    ledger = apps.get_model("ai_production", "ProductionLedger")
    alias = schema_editor.connection.alias
    receipt = ledger.objects.using(alias).filter(task_id=OuterRef("pk"), event="settle").order_by("created_at")
    task.objects.using(alias).filter(state="completed").update(
        completed_at=Subquery(receipt.values("created_at")[:1]),
    )


class Migration(migrations.Migration):
    dependencies = [("ai_production", "0007_productionquotareset")]

    operations = [
        migrations.AddField(model_name="productiontask", name="completed_at", field=models.DateTimeField(null=True)),
        migrations.RunPython(preserve_print_receipt_dates, migrations.RunPython.noop),
        migrations.DeleteModel(name="ProductionLedger"),
    ]
