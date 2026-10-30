import secrets
import json
import hashlib
import uuid
import time
from copy import deepcopy
from datetime import timedelta
from django.core.cache import cache
from django.utils.http import parse_etags
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Series, Template, Version, Upload, DownloadPlan, Event
from .domain import select, merge
from . import storage
from .access import visible_version, authorize


from .admin_support import Conflict, PresetAdmin, lock_template, preview


class SeriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Series
        fields = '__all__'


class TemplateSerializer(serializers.ModelSerializer):
    version = serializers.SerializerMethodField()
    production_sync = serializers.SerializerMethodField()
    has_draft_changes = serializers.SerializerMethodField()

    def get_version(self, obj):
        return obj.current.number if obj.current_id else 0

    def get_production_sync(self, obj):
        from .sync_protocol import sync_summary
        return sync_summary(obj)

    def get_has_draft_changes(self, obj):
        return bool(obj.current_id and obj.draft != obj.current.snapshot)

    import_statistics = serializers.SerializerMethodField()
    def get_import_statistics(self, obj):
        return self.context.get("import_statistics", {}).get(str(obj.pk))

    page_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    def get_page_count(self, obj):
        return len(obj.draft.get('pages', []))
    def get_cover_url(self, obj):
        cover = obj.draft.get('manifest', {}).get('coverPageID')
        page = next((p for p in obj.draft.get('pages', []) if p['data']['id'] == cover), None)
        return preview(obj.draft['keys'][page['data']['preview']['thumbnailPath']]) if page else None
    def validate_content_kind(self, value):
        if self.instance and self.instance.current_id and self.instance.content_kind != value:
            raise serializers.ValidationError('已发布素材不能变更类型，请新建对应类型的素材')
        return value

    class Meta:
        model = Template
        fields = ['id', 'content_kind', 'series', 'title', 'description', 'position', 'active', 'revision', 'current', 'page_count', 'cover_url', 'import_statistics', 'version', 'production_sync', 'has_draft_changes']
        read_only_fields = ['id', 'revision', 'current']


@transaction.atomic
def publish(obj, actor):
    if not obj.draft or not obj.draft.get('pages'):
        raise ValidationError('至少需要一页')
    snap = deepcopy(obj.draft)
    manifest = snap['manifest']
    manifest.update(templateBookID=str(obj.id), title=obj.title, seriesID=obj.series.slug, contentKind=obj.content_kind,
                    packageVersion=(obj.versions.order_by('-number').values_list('number', flat=True).first() or 0) + 1)
    from .search import documents, index_version, bump
    try:
        documents(obj, snap)
    except ValueError as exc:
        raise ValidationError(str(exc))
    obj.current = Version.objects.create(template=obj, number=manifest['packageVersion'], snapshot=snap, actor=actor)
    from material_library.lifecycle import bind_published_template
    bind_published_template(obj, obj.current)
    searchable_count = index_version(obj, obj.current)
    obj.draft = snap
    obj.revision += 1
    obj.save()
    Event.objects.create(actor=actor, template=obj, action='publish', detail={'version': obj.current.number})
    bump()
    return searchable_count


class SeriesAdmin(viewsets.ModelViewSet):
    permission_classes = [PresetAdmin]
    serializer_class = SeriesSerializer
    queryset = Series.objects.all()
    pagination_class = None

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.templates.exists():
            raise Conflict('请先移动系列下的手帐')
        obj.delete()
        return Response(status=204)


from .search_views import TemplateSearchMixin


class TemplateAdmin(TemplateSearchMixin, viewsets.ModelViewSet):
    permission_classes = [PresetAdmin]
    serializer_class = TemplateSerializer
    queryset = Template.objects.select_related('series', 'current').filter(audience='public')
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('series'):
            qs = qs.filter(series_id=self.request.query_params['series'])
        if self.request.query_params.get('content_kind'):
            qs = qs.filter(content_kind=self.request.query_params['content_kind'])
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['import_statistics'] = getattr(self, '_import_statistics', {})
        return context

    def list(self, request, *args, **kwargs):
        from .import_statistics import template_statistics
        objects = list(self.filter_queryset(self.get_queryset()))
        self._import_statistics = template_statistics([obj.pk for obj in objects])
        return Response(self.get_serializer(objects, many=True).data)

    @action(detail=False, methods=['get'], url_path='statistics-metadata')
    def statistics_metadata(self, request):
        from .import_statistics import statistics_metadata
        return Response(statistics_metadata())

    @action(detail=True, methods=['get'], url_path='page-statistics')
    def page_statistics(self, request, pk=None):
        from .import_statistics import page_statistics, statistics_metadata
        obj = self.get_object()
        number = request.query_params.get('version')
        if number is not None:
            try: number = int(number)
            except (TypeError, ValueError): raise ValidationError('版本号无效')
            version = get_object_or_404(obj.versions, number=number)
            versions = [version]
        else:
            versions = obj.versions.order_by('number')
        titles = {}
        for version in versions:
            for page in version.snapshot.get('pages', []):
                titles[page['data']['id']] = page['data']['title']
        current = {p['data']['id'] for p in obj.draft.get('pages', [])}
        counts = page_statistics(obj, number)
        return Response(dict(statistics_metadata(), pages=[
            dict(id=page_id, title=titles.get(page_id, page_id), count=counts.get(page_id, 0),
                 removed=page_id not in current) for page_id in sorted(titles.keys() | counts.keys())]))

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        obj = lock_template(kwargs['pk'], request.data)
        ser = self.get_serializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save(revision=obj.revision + 1)
        return Response(ser.data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        obj = lock_template(kwargs['pk'], request.data)
        obj.active = False
        obj.revision += 1
        obj.save()
        Event.objects.create(actor=request.user, template=obj, action='archive')
        return Response(status=204)

    @action(detail=True, methods=['get', 'put'])
    def pages(self, request, pk=None):
        if request.method == 'GET':
            obj = self.get_object()
            from .import_statistics import page_statistics
            counts = page_statistics(obj)
            return Response(dict(revision=obj.revision, pages=[dict(id=p['data']['id'], title=p['data']['title'], import_count=counts.get(p['data']['id'], 0),
                thumbnail=preview(obj.draft['keys'][p['data']['preview']['thumbnailPath']]),
                preview=preview(obj.draft['keys'][p['data']['preview']['largePath']]))
                for p in obj.draft.get('pages', [])], cover=obj.draft.get('manifest', {}).get('coverPageID')))
        with transaction.atomic():
            obj = lock_template(pk, request.data)
            try:
                obj.draft = select(obj.draft, request.data.get('page_ids', []))
            except (ValueError, KeyError) as exc:
                raise ValidationError(str(exc))
            titles = request.data.get('titles', {})
            for page in obj.draft['pages']:
                title = titles.get(page['data']['id'], page['data']['title'])
                if not isinstance(title, str) or not title.strip() or len(title) > 200:
                    raise ValidationError('页面标题长度需为 1–200 字符')
                if title != page['data']['title']:
                    page['data']['title'] = title
                    ref = next(r for r in obj.draft['manifest']['pages'] if r['id'] == page['data']['id'])
                    ref['title'] = title
                    data = json.dumps(page['data'], ensure_ascii=False, separators=(',', ':')).encode()
                    sha = hashlib.sha256(data).hexdigest()
                    key = storage.prefix() + 'blobs/sha256/' + sha
                    storage.bucket().put_object(key, data, headers={'Content-Type': 'application/json', 'x-oss-object-acl': 'private'})
                    obj.draft['keys'][ref['path']] = key
                    record = next(f for f in obj.draft['manifest']['files'] if f['path'] == ref['path'])
                    record.update(byteCount=len(data), sha256=sha)
            cover = request.data.get('cover_page_id')
            if cover:
                if cover not in request.data['page_ids']:
                    raise ValidationError('封面必须属于该手帐')
                obj.draft['manifest']['coverPageID'] = cover
                metadata = obj.draft['manifest'].get('pageMetadata', {})
                if metadata:
                    for page_id, meta in metadata.items():
                        if page_id == cover: meta['contentRole'] = 'front_cover'
                        elif meta.get('contentRole') == 'front_cover': meta['contentRole'] = 'content'
                    for unit in obj.draft['manifest'].get('readingUnits', []):
                        if cover in (unit.get('leftPageID'), unit.get('rightPageID')): unit['searchEnabled'] = False
            obj.revision += 1
            obj.save()
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def publish(self, request, pk=None):
        obj = lock_template(pk, request.data)
        count = publish(obj, request.user)
        return Response(dict(self.get_serializer(obj).data, searchable_spread_count=count))

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        return Response(list(self.get_object().versions.order_by('-number').values('number', 'created_at')))

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def rollback(self, request, pk=None):
        obj = lock_template(pk, request.data)
        version = get_object_or_404(obj.versions, number=request.data.get('version'))
        obj.draft = deepcopy(version.snapshot)
        publish(obj, request.user)
        return Response(self.get_serializer(obj).data)


class UploadSerializer(serializers.Serializer):
    template = serializers.UUIDField()
    revision = serializers.IntegerField(min_value=0)
    mode = serializers.ChoiceField(choices=['book', 'page'])
    size = serializers.IntegerField(min_value=1, max_value=1024**3)
    after_page = serializers.CharField(max_length=200, required=False, allow_blank=True)


class UploadAdmin(viewsets.GenericViewSet):
    permission_classes = [PresetAdmin]
    queryset = Upload.objects.all()

    def list(self, request):
        qs = self.get_queryset().order_by('-created_at')
        template = request.query_params.get('template')
        if template:
            qs = qs.filter(template_id=template)
        return Response(list(qs[:100].values('id', 'template_id', 'mode', 'size', 'status', 'error', 'created_at')))

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def retry(self, request, pk=None):
        obj = get_object_or_404(Upload.objects.select_for_update(), pk=pk)
        if obj.status not in ['failed', 'conflict']:
            raise ValidationError('只能重试失败或冲突任务')
        template = lock_template(obj.template_id, request.data)
        after = request.data.get('after_page', obj.after_page)
        if after and after not in [p['data']['id'] for p in template.draft.get('pages', [])]:
            raise ValidationError('插入位置已不存在')
        obj.revision = template.revision
        obj.after_page = after
        obj.status = 'queued'
        obj.error = ''
        obj.lease = None
        obj.lease_until = None
        obj.save()
        from .resource_queue import enqueue
        enqueue(obj)
        return Response({'status': obj.status}, status=202)

    def create(self, request):
        ser = UploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        obj = get_object_or_404(Template, pk=data.pop('template'), audience='public')
        if obj.revision != data['revision']:
            raise Conflict()
        uid = uuid.uuid4()
        key = storage.prefix() + f'staging/{uid}/source.diarypreset.zip'
        creds = storage.credentials(key)  # fail closed before persisting
        upload = Upload.objects.create(id=uid, template=obj, actor=request.user, object_key=key, **data)
        return Response(dict(id=str(upload.id), credentials=creds), status=201)

    def retrieve(self, request, pk=None):
        obj = self.get_object()
        return Response(dict(id=str(obj.id), status=obj.status, error=obj.error))

    @action(detail=True, methods=['post'])
    def refresh(self, request, pk=None):
        obj = self.get_object()
        if obj.status != 'uploading' or timezone.now() - obj.created_at > timedelta(days=1):
            raise ValidationError('上传会话已结束或过期')
        return Response(storage.credentials(obj.object_key))

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def complete(self, request, pk=None):
        obj = get_object_or_404(Upload.objects.select_for_update(), pk=pk)
        if obj.status != 'uploading':
            return Response(dict(id=str(obj.id), status=obj.status))
        if timezone.now() - obj.created_at > timedelta(days=1):
            raise ValidationError('上传会话已过期')
        if storage.bucket().head_object(obj.object_key).content_length != obj.size:
            raise ValidationError('上传文件大小不匹配')
        obj.status = 'queued'
        obj.save()
        from .resource_queue import enqueue
        enqueue(obj)
        return Response(dict(id=str(obj.id), status=obj.status), status=202)


class ProcessorPermission(BasePermission):
    def has_permission(self, request, view):
        expected = settings.DIARY_PRESETS_PROCESSOR_TOKEN
        return bool(expected and secrets.compare_digest(request.headers.get('X-Preset-Processor', ''), expected))


class Processor(APIView):
    """Poll from the dedicated processor (or an opt-in local development process)."""
    authentication_classes = []
    permission_classes = [ProcessorPermission]

    @transaction.atomic
    def post(self, request):
        obj = get_object_or_404(Upload.objects.select_for_update(), pk=request.data.get('id'))
        if obj.status != 'processing' or str(obj.lease) != request.data.get('lease') or obj.lease_until < timezone.now():
            raise Conflict('处理租约已过期')
        if request.data.get('error'):
            obj.status = 'failed'
            obj.error = str(request.data['error'])[:2000]
            obj.save()
            return Response({'status': obj.status})
        result = request.data.get('result')
        if not isinstance(result, dict) or len(result.get('pages', [])) not in range(1, 101):
            raise ValidationError('Invalid processor report')
        for key in result.get('keys', {}).values():
            if not key.startswith(storage.prefix() + 'blobs/'):
                raise ValidationError('Invalid blob prefix')
        template = Template.objects.select_for_update().get(pk=obj.template_id)
        obj.result = result
        if template.revision != obj.revision:
            obj.status = 'conflict'
            obj.error = '手帐已修改；处理成果保留，请重新选择插入位置'
        else:
            try:
                from .reading_units import retain_confirmed_metadata
                template.draft = merge(template.draft, result, obj.after_page) if obj.mode == 'page' else retain_confirmed_metadata(template.draft, result)
                publish(template, obj.actor)
                obj.status = 'published'
            except ValueError as exc:
                obj.status = 'failed'
                obj.error = str(exc)
        obj.save()
        return Response({'status': obj.status})


class Catalog(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = []
        content_kind = request.query_params.get('content_kind', 'journal')
        if content_kind not in ('journal', 'album', 'all'):
            raise ValidationError('content_kind 需为 journal/album/all')
        templates = Template.objects.filter(audience='public', active=True, series__active=True, current__isnull=False)
        if content_kind != 'all':
            templates = templates.filter(content_kind=content_kind)
        for template in templates.select_related('current', 'series')[:500]:
            try:
                schema_max = int(request.query_params.get('schema_max', 1))
            except ValueError:
                raise ValidationError('schema_max 无效')
            if template.current.snapshot['manifest'].get('schemaVersion', 1) > schema_max:
                compatible = template.versions.order_by('-number').filter(snapshot__manifest__schemaVersion=1).first()
                if not compatible:
                    continue
                template.current = compatible
            snap = template.current.snapshot
            cover = next(p for p in snap['pages'] if p['data']['id'] == snap['manifest']['coverPageID'])
            rows.append(dict(id=str(template.id), title=template.title, series=template.series.slug,
                content_kind=template.content_kind, version=template.current.number, page_count=len(snap['pages']),
                cover_url=preview(snap['keys'][cover['data']['preview']['thumbnailPath']])))
        return Response(dict(series=list(Series.objects.filter(active=True).exclude(slug='private-custom').values('slug', 'title')), books=rows))


class Browse(APIView):
    """Small, versioned projection, cached for less than the signed URL lifetime."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, number):
        # Always check publication visibility, including cache hits and conditional requests.
        version = visible_version(request.user, pk, number)
        window = int(time.time()) // 300
        expires_at = (window + 1) * 300
        key = f'diary-preset-browse-v2:{request.user.pk}:{version.pk}:{window}'
        cached = cache.get(key)
        if cached is None:
            snap = version.snapshot
            manifest = snap['manifest']
            body = dict(title=manifest['title'], page_size=manifest['pageSize'],
                        cover_page_id=manifest['coverPageID'], shell_page_id=manifest.get('shellPageID'),
                        expires_at=expires_at,
                        pages=[dict(id=p['data']['id'], title=manifest.get('pageMetadata', {}).get(p['data']['id'], {}).get('displayTitle', p['data']['title']),
                                    thumbnail_url=preview(snap['keys'][p['data']['preview']['thumbnailPath']]),
                                    preview_url=preview(snap['keys'][p['data']['preview']['largePath']]))
                               for p in snap['pages']])
            if manifest.get('schemaVersion') == 2:
                body['reading_units'] = manifest.get('readingUnits', [])
                body['page_metadata'] = manifest.get('pageMetadata', {})
            # Hash the actual representation: a rebuilt cache with new signatures gets a new ETag.
            etag = '"' + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() + '"'
            cached = (body, etag)
            cache.set(key, cached, timeout=max(1, expires_at - int(time.time())))
        body, etag = cached
        tags = parse_etags(request.headers.get('If-None-Match', ''))
        matches = '*' in tags or etag in [tag.removeprefix('W/') for tag in tags]
        response = Response(status=304) if matches else Response(body)
        response['ETag'] = etag
        response['Cache-Control'] = f'private, max-age={max(0, expires_at - int(time.time()))}'
        response['Vary'] = 'Authorization'
        return response


class Detail(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, number):
        version = visible_version(request.user, pk, number)
        from billing.access import require_content
        if version.template.audience == 'public': require_content(request, 'template', pk)
        snap = version.snapshot
        return Response(dict(manifest=snap['manifest'], page_data=[p['data'] for p in snap['pages']], pages=[dict(id=p['data']['id'], title=p['data']['title'],
            thumbnail_url=preview(snap['keys'][p['data']['preview']['thumbnailPath']]),
            preview_url=preview(snap['keys'][p['data']['preview']['largePath']])) for p in snap['pages']]))

    def post(self, request, pk, number):
        version = visible_version(request.user, pk, number)
        from billing.access import require_content
        if version.template.audience == 'public': require_content(request, 'template', pk)
        ids = request.data.get('page_ids')
        selection = request.data.get('selection')
        if selection is not None:
            if 'page_ids' in request.data or not isinstance(selection, dict) or selection.get('kind') != 'spread':
                raise ValidationError('无效的跨页选择')
            from .reading_units import page_ids, exclusion_reason
            manifest = version.snapshot['manifest']
            unit = next((u for u in manifest.get('readingUnits', []) if u['id'] == selection.get('unit_id')), None)
            if not unit or not unit.get('searchEnabled') or exclusion_reason(manifest, unit):
                raise ValidationError('此跨页不可添加')
            ids = page_ids(unit)
        if ids is None:
            ids = [p['data']['id'] for p in version.snapshot['pages']]
        try:
            snapshot = select(version.snapshot, ids)
        except (ValueError, KeyError) as exc:
            raise ValidationError(str(exc))
        plan = DownloadPlan.objects.create(owner=request.user, version=version, snapshot=snapshot,
                                          expires_at=timezone.now() + timedelta(days=7))
        return Response(dict(id=str(plan.id), manifest=snapshot['manifest']), status=201)


class PlanURLs(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(DownloadPlan, pk=pk, owner=request.user)
        authorize(request.user, plan.version)
        from billing.access import require_content
        if plan.version.template.audience == 'public': require_content(request, 'template', plan.version.template_id)
        if plan.expires_at <= timezone.now():
            plan.expires_at = timezone.now() + timedelta(days=7)
            plan.save(update_fields=['expires_at'])
        paths = request.data.get('paths', [])
        if not isinstance(paths, list) or not 1 <= len(paths) <= 50 or any(not isinstance(p, str) or p not in plan.snapshot['keys'] for p in paths):
            raise ValidationError('Invalid resource selection')
        return Response({p: storage.sign(plan.snapshot['keys'][p]) for p in paths})
