from django.db import migrations
from django.db.models import Q


def retire_health_scenes(apps, schema_editor):
    Scene = apps.get_model('notification_center', 'NotificationBusinessScene')
    Scene.objects.using(schema_editor.connection.alias).filter(
        Q(key__startswith='medical.') | Q(key__startswith='task.') | Q(key__startswith='ai.job.') | Q(key__startswith='ai.content.') | Q(key__startswith='system.app_version.')
    ).update(status='retired')


class Migration(migrations.Migration):
    dependencies = [('notification_center', '0005_membership_pro_trial_fallback_routing')]
    operations = [migrations.RunPython(retire_health_scenes, migrations.RunPython.noop)]
