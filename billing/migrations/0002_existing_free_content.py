from django.db import migrations

def forwards(apps,schema_editor):
    Offer=apps.get_model('billing','ContentOffer');Policy=apps.get_model('billing','ContentPolicyRevision')
    Template=apps.get_model('diary_presets','Template');Library=apps.get_model('material_library','MaterialLibrary')
    alias=schema_editor.connection.alias
    for kind,objects in [('template',Template.objects.using(alias).filter(audience='public',current__isnull=False)),('sticker_library',Library.objects.using(alias).filter(current__isnull=False))]:
        for obj in objects.iterator():
            offer,created=Offer.objects.using(alias).get_or_create(target_kind=kind,target_id=obj.pk,ownership_scope='personal_permanent',defaults={'title':obj.title,'state':'active'})
            if created:
                policy=Policy.objects.using(alias).create(offer=offer,revision=1,access_mode='free',terms_version='legacy-free-v1',content_scope_snapshot={'target_kind':kind,'target_id':str(obj.pk)})
                offer.current_policy_revision=policy;offer.save(using=alias)

class Migration(migrations.Migration):
    dependencies=[('billing','0001_initial'),('diary_presets','0009_template_content_kind'),('material_library','0009_materialsyncnonce_alter_materiallibrary_options_and_more')]
    operations=[migrations.RunPython(forwards,migrations.RunPython.noop)]
