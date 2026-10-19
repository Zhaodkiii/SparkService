from django.db import migrations


TERMS = (
    '制作开始后不可取消或改稿；签收后7日内可反馈质量问题，经核实后安排补印或补寄；'
    '印制费和运费均为¥0。'
)


def open_catalog(apps, schema_editor):
    Product = apps.get_model('print_orders', 'Product')
    db = schema_editor.connection.alias
    for title in ('A5', 'B5（ISO）'):
        product = Product.objects.using(db).filter(title=title).first()
        if not product:
            continue
        ready = bool(
            product.proof_approved and product.proof_note.strip()
            and product.paper.strip() and product.binding.strip()
            and product.free_printing and product.regions
            and product.lead_time.strip() and TERMS.strip()
            and product.width_mm and product.height_mm
            and product.min_pages <= product.max_pages
        )
        Product.objects.using(db).filter(pk=product.pk).update(
            terms=TERMS,
            active=ready,
            revision=product.revision + 1,
        )


class Migration(migrations.Migration):
    dependencies = [('print_orders', '0007_record_standard_proofs_and_lead_time')]
    operations = [migrations.RunPython(open_catalog, migrations.RunPython.noop)]
