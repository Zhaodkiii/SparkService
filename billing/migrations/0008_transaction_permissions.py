from django.db import migrations

def setup(apps,schema_editor):
    Permission=apps.get_model('backoffice','AdminPermission')
    for code,name,kind,path in [('menu:transactions','交易中心','menu','/billing/transactions'),('billing.view_transactions','查看用户资产与交易','api',''),('billing.sync_transactions','同步用户资产快照','api','')]:
        Permission.objects.using(schema_editor.connection.alias).get_or_create(code=code,defaults={'name':name,'permission_type':kind,'path':path,'parent_code':'' if kind=='menu' else 'menu:transactions','is_active':True})

class Migration(migrations.Migration):
    dependencies=[('billing','0007_storepayment')]
    operations=[migrations.RunPython(setup,migrations.RunPython.noop)]
