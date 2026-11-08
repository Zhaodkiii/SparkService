from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model('ai_runtime', 'Channel').objects.get_or_create(pk=1)
    permission = apps.get_model('backoffice', 'AdminPermission')
    permission.objects.update_or_create(code='menu:ai:runtime', defaults={
        'name': 'AI 服务配置', 'permission_type': 'menu', 'path': '/ai-config/runtime',
        'parent_code': 'menu:ai', 'is_active': True})
    for code, name in [('edit', '编辑配置'), ('credential', '维护凭证'), ('test', '测试配置'),
                       ('publish', '发布配置'), ('control', '停用服务'), ('audit', '配置审计')]:
        permission.objects.update_or_create(code='button:ai:runtime:'+code, defaults={
            'name': name, 'permission_type': 'button', 'parent_code': 'menu:ai:runtime', 'is_active': True})


class Migration(migrations.Migration):
    dependencies = [('ai_runtime', '0001_initial'), ('backoffice', '0007_retire_legacy_ai_permissions')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
