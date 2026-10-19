from django.db import migrations, models


def use_optional_shell(apps, schema_editor):
    Product = apps.get_model('print_orders', 'Product')
    for product in Product.objects.using(schema_editor.connection.alias).all():
        product.cover_mode = 'optional_shell'
        product.description = product.description.replace('正封面、封底独立交付，内页按阅读顺序交付', '有外壳时单独交付外壳，全部内容页按阅读顺序交付')
        product.revision += 1
        product.save(update_fields=['cover_mode', 'description', 'revision'])


class Migration(migrations.Migration):
    dependencies = [('print_orders', '0008_open_a5_b5_catalog')]
    operations = [
        migrations.AlterField(model_name='product', name='cover_mode', field=models.CharField(default='optional_shell', max_length=32)),
        migrations.RunPython(use_optional_shell, migrations.RunPython.noop),
    ]
