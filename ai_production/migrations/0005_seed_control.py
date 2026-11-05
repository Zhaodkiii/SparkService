from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model("ai_production", "ProductionControl").objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("ai_production", "0004_productioncontrol_productionpolicy_publish_key")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
