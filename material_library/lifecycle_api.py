from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from diary_presets.models import Template
from .models import *
from .management_api import Admin, audit, clean_text
from .catalog_v2 import Conflict, public_libraries
from .lifecycle import link_json, impact, scan_cleanup, execute_cleanup, cleanup_job_json


def links_response(template):
    return dict(template_id=str(template.pk), template_title=template.title,
                items=[link_json(l) for l in TemplateMaterialLink.objects.filter(template=template).select_related('template','library','library_version')],
                note='此配置在下一次发布整本手帐时生效。已发布版本和用户作品不变。')


def update_link(request, template, library=None):
    typ = library.library_type if library else request.data.get('type', 'sticker')
    if typ not in ('sticker','background'): raise ValidationError('无效素材类型')
    row = TemplateMaterialLink.objects.select_for_update().filter(template=template, library_type=typ).first()
    actual = row.revision if row else 0
    if request.data.get('expected_revision') != actual: raise Conflict('关联已更新，请刷新后重试')
    if request.data.get('linked') is False:
        if library and row and row.library_id != library.pk: raise Conflict('该手帐已更换配套包，请刷新')
        target = None; version = None
    else:
        if request.data.get('linked') is not True: raise ValidationError('linked 必须为布尔值')
        library_id = library.pk if library else serializers.UUIDField().run_validation(request.data.get('library_id'))
        target = get_object_or_404(public_libraries().select_for_update(), pk=library_id, library_type=typ)
        if not target.active or not target.current_id: raise ValidationError('只能关联已发布且上架的素材包')
        version = get_object_or_404(target.versions, number=serializers.IntegerField(min_value=1).run_validation(request.data.get('library_version')))
    if not row: row = TemplateMaterialLink(template=template, library_type=typ, revision=0)
    if row.pk and row.library_id == (target.pk if target else None) and row.library_version_id == (version.pk if version else None):
        return row
    previous = str(row.library_id) if row.library_id else None
    row.library=target; row.library_version=version; row.actor=request.user; row.revision+=1; row.save()
    audit(request, target or library, 'book-link' if target else 'book-unlink', dict(template_id=str(template.pk),type=typ,
          previous_library_id=previous, library_id=str(target.pk) if target else None,
          version=version.number if version else None, revision=row.revision))
    return row


class TemplateLinks(Admin):
    def get(self, request, template):
        return Response(links_response(get_object_or_404(Template, pk=template, audience='public')))

    @transaction.atomic
    def post(self, request, template):
        book = get_object_or_404(Template.objects.select_for_update(), pk=template, audience='public')
        update_link(request, book)
        return Response(links_response(book))


class LibraryLinks(Admin):
    def get(self, request, pk):
        library = get_object_or_404(public_libraries(), pk=pk)
        return Response(dict(items=[link_json(l) for l in library.book_links.select_related('template','library','library_version')],
            versions=list(library.versions.order_by('-number').values_list('number',flat=True))))

    @transaction.atomic
    def post(self, request, pk):
        template_id = serializers.UUIDField().run_validation(request.data.get('template_id'))
        book = get_object_or_404(Template.objects.select_for_update(), pk=template_id, audience='public')
        library = get_object_or_404(public_libraries().select_for_update(), pk=pk)
        row = update_link(request, book, library)
        return Response(link_json(row))


class DeletionPreview(Admin):
    def get(self, request, pk):
        library = get_object_or_404(public_libraries(include_deleted=True), pk=pk)
        result = impact(library)
        result['token'] = signing.dumps(dict(id=str(pk), revision=library.state_revision), salt='material-delete')
        return Response(result)


class Recycle(Admin):
    @transaction.atomic
    def post(self, request, pk):
        library = get_object_or_404(public_libraries(include_deleted=True).select_for_update(), pk=pk)
        if request.data.get('expected_state_revision') != library.state_revision: raise Conflict()
        operation = request.data.get('operation')
        if operation == 'restore':
            if library.deleted_at is None: return Response(dict(state_revision=library.state_revision))
            library.deleted_at=None; library.deletion_reason=''
            # Restoring never silently re-publishes or reattaches books.
            library.active=False
        elif operation == 'delete':
            try: token=signing.loads(request.data.get('token',''),salt='material-delete',max_age=600)
            except (signing.BadSignature, TypeError): raise Conflict('删除预览已过期，请重新检查')
            if token != dict(id=str(pk),revision=library.state_revision): raise Conflict()
            if request.data.get('confirm_title') != library.title: raise ValidationError('请输入完整素材包名称以确认删除')
            if library.deleted_at: return Response(dict(state_revision=library.state_revision))
            if library.book_links.filter(library__isnull=False).exists(): raise Conflict('请先取消全部手帐关联，再删除整套')
            from .tasks import ACTIVE
            if MaterialSyncTask.objects.filter(library_uuid=pk,state__in=ACTIVE).exists(): raise Conflict('同步任务尚未结束，暂不能删除整套')
            library.deletion_reason=clean_text(request.data.get('reason',''),300)
            library.deleted_at=timezone.now(); library.active=False
        else: raise ValidationError('无效操作')
        library.state_revision+=1; library.save(update_fields=['deleted_at','deletion_reason','active','state_revision'])
        audit(request, library, 'recycle-'+operation, dict(reason=library.deletion_reason))
        return Response(dict(state_revision=library.state_revision, deleted_at=library.deleted_at))


class CleanupScan(Admin):
    def get(self, request):
        jobs=MaterialCleanupJob.objects.order_by('-created_at')[:20]
        return Response([cleanup_job_json(j) for j in jobs])

    def post(self, request):
        job=scan_cleanup(request.user)
        audit(request,None,'cleanup-scan',dict(job_id=str(job.pk),total=len(job.entries)))
        return Response(cleanup_job_json(job),status=201)


class CleanupExecute(Admin):
    def post(self, request, pk):
        get_object_or_404(MaterialCleanupJob,pk=pk)
        job=execute_cleanup(pk)
        audit(request,None,'cleanup-execute',dict(job_id=str(pk),state=job.state))
        return Response(cleanup_job_json(job))
