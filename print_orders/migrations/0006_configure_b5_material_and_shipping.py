from django.db import migrations


def configure_b5(apps, schema_editor):
    Product = apps.get_model('print_orders', 'Product')
    db = schema_editor.connection.alias
    source = Product.objects.using(db).filter(title='A5').first()
    target = Product.objects.using(db).filter(title='B5（ISO）').first()
    if not source or not target:
        return
    Product.objects.using(db).filter(pk=target.pk).update(
        paper=source.paper,
        binding=source.binding,
        regions=list(source.regions or []),
        free_printing=True,
        base_fen=0,
        page_fen=0,
        shipping_fen=0,
        active=False,
        proof_approved=False,
        revision=target.revision + 1,
    )


class Migration(migrations.Migration):
    dependencies = [('print_orders', '0005_standardize_a5_b5_specs')]
    operations = [migrations.RunPython(configure_b5, migrations.RunPython.noop)]
