from django.db import migrations


def backfill(apps,schema_editor):
    Version=apps.get_model('material_library','LibraryVersion')
    Binding=apps.get_model('material_library','TemplateLibraryBinding')
    for version in Version.objects.exclude(preset_version_id=None).select_related('library').order_by('-number').iterator():
        Binding.objects.get_or_create(preset_version_id=version.preset_version_id,library_type=version.library.library_type,defaults={'library_version_id':version.pk})


class Migration(migrations.Migration):
    dependencies=[('material_library','0003_templatelibrarybinding')]
    operations=[migrations.RunPython(backfill,migrations.RunPython.noop)]
