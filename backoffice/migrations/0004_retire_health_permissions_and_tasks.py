from django.db import migrations
from django.db.models import Q


def retire_health_entries(apps, schema_editor):
    alias = schema_editor.connection.alias
    Permission = apps.get_model('backoffice', 'AdminPermission')
    Permission.objects.using(alias).filter(
        Q(code__contains='medical_data') | Q(code__contains='quick_questions') | Q(code__startswith='content.') | Q(code__startswith='menu:articles') | Q(code__startswith='menu:conversations') | Q(code__startswith='menu:version') | Q(code__startswith='menu:subscriptions') | Q(code__startswith='button:subscription:') | Q(code__startswith='button:version:')
    ).update(is_active=False)
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.using(alias).filter(
        Q(task__startswith='medical.') | Q(task__startswith='nutrition.')
        | Q(task__startswith='task_system.') | Q(task__startswith='zdk_migration.')
        | Q(task__startswith='hospital_care.') | Q(task__startswith='content.') | Q(task__startswith='chat_sync.') | Q(task__startswith='subscriptions.')
    ).update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [
        ('backoffice', '0003_ensure_medical_data_stats_indexes'),
        ('django_celery_beat', '0001_initial'),
    ]
    operations = [migrations.RunPython(retire_health_entries, migrations.RunPython.noop)]
