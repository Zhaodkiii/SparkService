from django.db import migrations


def finish_legacy_photo_jobs(apps, schema_editor):
    Job = apps.get_model('diary_customizations', 'Job')
    Asset = apps.get_model('diary_customizations', 'Asset')
    database = schema_editor.connection.alias
    # These legacy states were only reached after upload completion. Keep the
    # existing OSS key; this migration performs database operations only.
    jobs = Job.objects.using(database).filter(kind='asset', status__in=['queued', 'processing', 'failed'])
    for job in jobs.select_related('asset', 'request').iterator():
        if not job.asset_id or job.asset.deleted_at or job.request.deleted_at or job.request.status in ('cancelled', 'rejected'):
            Job.objects.using(database).filter(pk=job.pk).update(status='abandoned', lease=None, lease_until=None)
            continue
        key = job.asset.object_key if job.asset.status == 'ready' and job.asset.object_key else job.object_key
        Asset.objects.using(database).filter(pk=job.asset_id).update(object_key=key, status='ready')
        Job.objects.using(database).filter(pk=job.pk).update(
            status='ready', error='', lease=None, lease_until=None,
            result={'object_key': key, 'completion': 'legacy_upload_completed'})


class Migration(migrations.Migration):
    dependencies = [('diary_customizations', '0003_delivery_published_number_and_more')]
    operations = [migrations.RunPython(finish_legacy_photo_jobs, migrations.RunPython.noop)]
