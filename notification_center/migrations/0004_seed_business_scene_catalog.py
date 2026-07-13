from django.db import migrations


def seed_catalog(apps, schema_editor):
    # Importing the versioned definitions is intentional: this data migration
    # projects the catalog that belongs to this release, without using live model
    # methods or triggering providers/tasks.
    from notification_center.business_scenes import SCENE_CATALOG

    Scene = apps.get_model("notification_center", "NotificationBusinessScene")
    for definition in SCENE_CATALOG:
        defaults = definition.defaults(topic=None)
        defaults.pop("key", None)
        Scene.objects.update_or_create(key=definition.key, defaults=defaults)


class Migration(migrations.Migration):
    dependencies = [("notification_center", "0003_notificationbusinessscene_and_more")]

    operations = [migrations.RunPython(seed_catalog, migrations.RunPython.noop)]
