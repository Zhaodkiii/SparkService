from django.db import migrations


def update_permissions(apps, schema_editor):
    permission = apps.get_model("backoffice", "AdminPermission")
    permission.objects.filter(code__in=["button:ai:production:refund", "button:ai:production:release"]).delete()
    permission.objects.update_or_create(code="button:ai:production:adjust", defaults={
        "name": "纠正模型用量", "permission_type": "button", "parent_code": "menu:ai:production",
    })


class Migration(migrations.Migration):
    dependencies = [("backoffice", "0008_delete_retired_ai_configuration")]
    operations = [migrations.RunPython(update_permissions, migrations.RunPython.noop)]
