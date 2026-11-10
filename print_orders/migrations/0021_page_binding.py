from django.db import migrations, models


def keep_existing_terms(apps, schema_editor):
    Enrollment = apps.get_model('print_orders', 'PrintEnrollment')
    Enrollment.objects.filter(plan__source='pages', plan__ai_pages_only=False).update(legacy_page_rule=True)


class Migration(migrations.Migration):
    dependencies = [('print_orders', '0020_ai_page_evidence')]
    operations = [
        migrations.AddField('printenrollment', 'legacy_page_rule', models.BooleanField(default=False)),
        migrations.CreateModel(name='PrintPageBinding', fields=[
            ('task_id', models.UUIDField(primary_key=True, serialize=False)),
            ('book_id', models.UUIDField()),
        ]),
        migrations.RunPython(keep_existing_terms, migrations.RunPython.noop),
    ]
