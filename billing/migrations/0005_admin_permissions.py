from django.db import migrations

CODES=[('billing.view_pricing','查看收费与钻石交易'),('billing.change_pricing_draft','编辑收费策略草稿'),('billing.publish_pricing','发布收费策略与定制报价'),('billing.resolve_refund','申请钻石补偿')]
def forwards(apps,schema_editor):
    Permission=apps.get_model('backoffice','AdminPermission')
    alias=schema_editor.connection.alias
    Permission.objects.using(alias).get_or_create(code='menu:billing',defaults={'name':'收费与权限','permission_type':'menu','path':'/billing','is_active':True})
    for code,name in CODES:
        Permission.objects.using(alias).get_or_create(code=code,defaults={'name':name,'permission_type':'api','parent_code':'menu:billing','is_active':True})
    # Existing superusers already bypass checks. Ordinary operator roles need explicit assignment.

class Migration(migrations.Migration):
    dependencies=[('billing','0004_alter_customizationfunding_request'),('backoffice','0001_initial')]
    operations=[migrations.RunPython(forwards,migrations.RunPython.noop)]
