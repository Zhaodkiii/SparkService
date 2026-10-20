from django.db import migrations

SCENES={'info_requested':'定制待补充','due_changed':'定制日期调整','rejected':'定制无法制作','cancelled':'定制已取消',
 'delivered':'定制首次交付','redelivered':'定制修订交付','delivery_withdrawn':'定制交付撤回','delivery_rolled_back':'定制版本回滚','pending_reminder':'定制人工提醒'}
def seed(apps,schema_editor):
    Topic=apps.get_model('notification_center','NotificationTopic');Scene=apps.get_model('notification_center','NotificationBusinessScene')
    topic,_=Topic.objects.get_or_create(key='diary.customization',defaults={'name':'定制进度与成品提醒','category':'transactional','requires_user':True,'default_channels':['apns']})
    Template=apps.get_model('notification_center','NotificationTemplate');Version=apps.get_model('notification_center','NotificationTemplateVersion')
    bodies={'info_requested':'你的定制需要补充资料，请打开查看','delivered':'你的专属手帐已完成，快来查看吧','redelivered':'你的专属手帐已更新，请查看新版'}
    for action,title in SCENES.items():
        key='diary.customization.'+action
        template,_=Template.objects.get_or_create(key=key,defaults=dict(name=title,topic_key='diary.customization',title_template='专属定制',body_template=bodies.get(action,'你的定制有新的更新，请打开查看'),default_channels=['apns']))
        Version.objects.get_or_create(template=template,version=1,locale='zh-CN',defaults=dict(status='published',title_template=template.title_template,body_template=template.body_template))
        Scene.objects.get_or_create(key='diary.customization.'+action,defaults=dict(domain='diary',business_type='diary.customization',event_name=action,
            display_name=title,topic=topic,default_template_key=key,category='transactional',severity='info',status='active',contract_version=1,
            default_routing={'mode':'parallel','steps':[{'channel':'apns','required':False}]},preference_policy='opt_out',quiet_hour_policy='respect',owner_team='traveldiary'))
class Migration(migrations.Migration):
    dependencies=[('diary_customizations','0001_initial'),('notification_center','0006_retire_health_scenes')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]
