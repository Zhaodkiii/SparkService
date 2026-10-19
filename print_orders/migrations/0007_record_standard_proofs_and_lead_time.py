from django.db import migrations
from django.utils import timezone


def record_proofs(apps, schema_editor):
    Product = apps.get_model('print_orders', 'Product')
    db = schema_editor.connection.alias
    for title, width, height in [('A5', 148, 210), ('B5（ISO）', 176, 250)]:
        product = Product.objects.using(db).filter(title=title).first()
        if not product:
            continue
        Product.objects.using(db).filter(pk=product.pk).update(
            proof_approved=True,
            proof_note=(
                f'用户确认：标准 {title} 实物打样通过。规格 {width}×{height} mm；'
                f'纸张：{product.paper}；装订：{product.binding}；'
                '无出血，正封面与封底独立交付，内页按阅读顺序交付。'
            ),
            proof_at=timezone.now(),
            proof_by='用户确认',
            lead_time='制作周期：3天',
            active=False,
            revision=product.revision + 1,
        )


class Migration(migrations.Migration):
    dependencies = [('print_orders', '0006_configure_b5_material_and_shipping')]
    operations = [migrations.RunPython(record_proofs, migrations.RunPython.noop)]
