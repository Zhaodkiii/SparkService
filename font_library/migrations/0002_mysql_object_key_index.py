"""Compatibility for databases which applied the original SQLite-friendly schema."""
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('font_library', '0001_initial')]
    operations = [migrations.AlterField(
        model_name='fontasset', name='object_key',
        field=models.CharField(max_length=255, unique=True),
    )]
