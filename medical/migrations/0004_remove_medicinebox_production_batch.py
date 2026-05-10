from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0003_medicinebox_medicine_name_and_drop_stock_fields"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="medicinebox",
            name="production_batch",
        ),
    ]
