"""Book associations, reversible deletion and metadata-only OSS cleanup.

Formal blobs are shared across environments. Until a global reference registry
exists, they are reported as protected and NEVER passed to OSS DELETE.
"""
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import (MaterialLibrary, TemplateMaterialLink, TemplateLibraryBinding,
                     MaterialUpload, MaterialCleanupJob, LibraryVersion, MaterialRevision)
from diary_presets.storage import bucket, prefix


@transaction.atomic
def bind_published_template(template, version):
    from diary_presets.models import Template
    # Same lock as association edits, so a publish sees one coherent configuration.
    Template.objects.select_for_update().get(pk=template.pk)
    for link in TemplateMaterialLink.objects.filter(template=template, library__isnull=False).order_by('library_id'):
        library = MaterialLibrary.objects.select_for_update().get(pk=link.library_id)
        if library.deleted_at or not library.active or not link.library_version_id:
            raise ValidationError('配套素材包未发布、已下架或已删除，请先处理配套关联')
        if link.library_version.library_id != library.pk:
            raise ValidationError('配套素材版本与包不匹配')
        TemplateLibraryBinding.objects.get_or_create(preset_version=version, library_type=link.library_type,
                                                    defaults={'library_version_id': link.library_version_id})


def link_json(link):
    return dict(template_id=str(link.template_id), template_title=link.template.title,
                type=link.library_type, library_id=str(link.library_id) if link.library_id else None,
                library_title=link.library.title if link.library_id else None,
                library_version=link.library_version.number if link.library_version_id else None,
                revision=link.revision, updated_at=link.updated_at)


def impact(library):
    versions = library.versions.all()
    hashes = set()
    for content in versions.values_list('content', flat=True):
        hashes.update(content.get('previews', []))
        if content.get('cover'): hashes.add(content['cover'])
    try:
        draft = library.draft.content
        hashes.update(draft.get('previews', []))
        if draft.get('cover'): hashes.add(draft['cover'])
        revision_ids = [i['revision'] for i in draft.get('items', [])]
    except MaterialLibrary.draft.RelatedObjectDoesNotExist:
        revision_ids = []
    from django.db.models import Q
    for r in MaterialRevision.objects.filter(Q(libraryitem__version__library=library) | Q(pk__in=revision_ids)).distinct():
        hashes.update([r.resource_id, r.thumbnail_id])
    from .models import ResourceBlob
    blobs = ResourceBlob.objects.filter(pk__in=hashes)
    return dict(id=str(library.pk), title=library.title, state_revision=library.state_revision,
                deleted_at=library.deleted_at,
                links=[link_json(l) for l in library.book_links.select_related('template','library','library_version')],
                historical_bindings=list(TemplateLibraryBinding.objects.filter(library_version__library=library).values(
                    'preset_version__template__title', 'preset_version__number', 'library_version__number')),
                versions=versions.count(), materials=library.current.items.count() if library.current_id else 0,
                resources=blobs.count(), protected_bytes=sum(blobs.values_list('byte_size', flat=True)),
                reclaimable_bytes=0,
                cleanup_reason='正式资源保留：历史版本、共享素材及跨环境引用尚不能完整排除；删除整套仅移入回收站。')


def cleanup_job_json(job):
    entries = job.entries
    return dict(id=str(job.pk), state=job.state, created_at=job.created_at, updated_at=job.updated_at,
                total=len(entries), completed=sum(e['state']=='deleted' for e in entries),
                failed=sum(e['state']=='failed' for e in entries), entries=entries,
                note='仅删除超过 7 天且上传授权已过期的临时文件。正式原图、缩略图、封面、展示图均受保护。')


def cleanup_candidates(days=7):
    now = timezone.now()
    rows = MaterialUpload.objects.filter(updated_at__lt=now-timedelta(days=max(7,days)), expires_at__lt=now,
                                         staging_cleaned_at__isnull=True).order_by('updated_at','pk')[:200]
    return [dict(upload_id=str(u.pk), name=u.name, state='pending', error='') for u in rows
            if u.object_key.startswith(prefix()+'material-uploads/')]


def scan_cleanup(actor, days=7):
    return MaterialCleanupJob.objects.create(actor=actor, entries=cleanup_candidates(days))


@transaction.atomic
def execute_cleanup(pk):
    # A persistent job lock serializes retries; each upload lock excludes late confirmation.
    job = MaterialCleanupJob.objects.select_for_update().get(pk=pk)
    if job.state == 'completed': return job
    oss = None
    processed = 0
    pending = any(e['state'] == 'pending' for e in job.entries)
    for entry in job.entries:
        if entry['state'] != ('pending' if pending else 'failed'): continue
        if processed >= 10: break
        processed += 1
        upload = MaterialUpload.objects.select_for_update().filter(pk=entry['upload_id']).first()
        if not upload or upload.staging_cleaned_at:
            entry.update(state='deleted', error=''); continue
        now = timezone.now()
        if (upload.updated_at >= now-timedelta(days=7) or upload.expires_at >= now
                or not upload.object_key.startswith(prefix()+'material-uploads/')):
            entry.update(state='blocked', error='上传会话发生变化或不属于允许的临时目录'); continue
        try:
            oss = oss or bucket()
            oss.delete_object(upload.object_key)
            if upload.upload_metadata: oss.delete_object(upload.object_key+'/thumbnail')
            upload.staging_cleaned_at = now
            if upload.state != 'verified': upload.state='expired'
            upload.save(update_fields=['staging_cleaned_at','state'])
            entry.update(state='deleted', error='')
        except Exception:
            # Never persist OSS exception strings containing credentials or URLs.
            entry.update(state='failed', error='OSS 删除失败，可重试；正式资源未删除')
    states = {e['state'] for e in job.entries}
    job.state = 'pending' if 'pending' in states else 'partial' if states & {'failed','blocked'} else 'completed'
    job.save(update_fields=['state','entries','updated_at'])
    return job
