from django.db import migrations


def retire(apps, schema_editor):
    permission = apps.get_model("backoffice", "AdminPermission")
    codes = [
        "menu:ai:scenario", "menu:ai:models", "menu:ai:small_tasks",
        "menu:ai:provider", "menu:ai:trial",
        "button:user:pro:grant", "button:user:pro:recycle",
    ]
    permission.objects.filter(code__in=codes).update(is_active=False)
    permission.objects.filter(parent_code__in=codes).update(is_active=False)
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(
        task__startswith="ai_config."
    ).update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [("backoffice", "0006_contentsyncbatch_content_sync_recent")]
    operations = [migrations.RunPython(retire, migrations.RunPython.noop)]
