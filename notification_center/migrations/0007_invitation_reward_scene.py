from django.db import migrations

def seed(apps,schema_editor):
    from notification_center.business_scenes import SCENE_BY_KEY
    definition=SCENE_BY_KEY['growth.invitation.reward_issued']
    defaults=definition.defaults(topic=None);defaults.pop('key',None)
    apps.get_model('notification_center','NotificationBusinessScene').objects.update_or_create(key=definition.key,defaults=defaults)

class Migration(migrations.Migration):
    dependencies=[('notification_center','0006_retire_health_scenes')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]
