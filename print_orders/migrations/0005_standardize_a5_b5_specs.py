from django.db import migrations


def standardize_specs(apps, schema_editor):
    Product = apps.get_model('print_orders', 'Product')
    db = schema_editor.connection.alias
    common = {
        'active': False,
        'free_printing': True,
        'base_fen': 0,
        'page_fen': 0,
        'shipping_fen': 0,
        'duplex': True,
        'min_pages': 2,
        'max_pages': 200,
        'max_quantity': 10,
        'cover_mode': 'separate_front_back',
    }
    a5 = Product.objects.using(db).filter(title='A5').order_by('id').first()
    if a5:
        old_width, old_height = a5.width_mm, a5.height_mm
        old_note = (a5.proof_note or '').strip()
        old_record = ''
        if a5.proof_approved or a5.proof_at or a5.proof_by or old_note:
            date = a5.proof_at.strftime('%Y-%m-%d %H:%M UTC') if a5.proof_at else '时间未记录'
            old_record = (
                f'历史打样记录（旧规格 {old_width}×{old_height} mm）：{old_note or "打样通过"}；'
                f'记录人：{a5.proof_by or "未记录"}；时间：{date}。'
                '该记录不适用于标准 A5 新规格，须重新实物打样。'
            )
        Product.objects.using(db).filter(pk=a5.pk).update(
            **common,
            width_mm=148,
            height_mm=210,
            description='标准 A5 · 148 × 210 mm；当前免费印制。无出血；正封面、封底独立交付，内页按阅读顺序交付。',
            proof_approved=False,
            proof_note=old_record,
            revision=a5.revision + 1,
        )

    b5 = Product.objects.using(db).filter(title__in=['B5', 'B5（ISO）']).order_by('id').first()
    if b5:
        Product.objects.using(db).filter(pk=b5.pk).update(
            **common,
            title='B5（ISO）',
            width_mm=176,
            height_mm=250,
            description='标准 ISO B5 · 176 × 250 mm；当前免费印制。无出血；正封面、封底独立交付，内页按阅读顺序交付。',
            proof_approved=False,
            proof_note='',
            proof_at=None,
            proof_by='',
            revision=b5.revision + 1,
        )


class Migration(migrations.Migration):
    dependencies = [('print_orders', '0004_filecleanup')]
    operations = [migrations.RunPython(standardize_specs, migrations.RunPython.noop)]
