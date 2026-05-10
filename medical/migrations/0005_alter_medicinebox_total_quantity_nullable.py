from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0004_remove_medicinebox_production_batch"),
    ]

    operations = [
        migrations.AlterField(
            model_name="medicinebox",
            name="total_quantity",
            field=models.DecimalField(
                blank=True,
                db_comment="总数量（服药扣减后同步减少，可空）",
                decimal_places=2,
                max_digits=10,
                null=True,
            ),
        ),
    ]
