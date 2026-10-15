import secrets
import json
import hashlib
import uuid
from copy import deepcopy
from datetime import timedelta
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


class Conflict(APIException):
    status_code = 409
    default_detail = '内容已修改，请刷新后重试'


class PresetAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_active and
                    (request.user.is_superuser or request.user.has_perm('diary_presets.change_template')))


class SeriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Series
        fields = '__all__'


class TemplateSerializer(serializers.ModelSerializer):
    page_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    def get_page_count(self, obj):
        return len(obj.draft.get('pages', []))
    def get_cover_url(self, obj):
        cover = obj.draft.get('manifest', {}).get('coverPageID')
        page = next((p for p in obj.draft.get('pages', []) if p['data']['id'] == cover), None)
        return preview(obj.draft['keys'][page['data']['preview']['thumbnailPath']]) if page else None
    class Meta:
        model = Template
        fields = ['id', 'series', 'title', 'description', 'position', 'active', 'revision', 'current', 'page_count', 'cover_url']
        read_only_fields = ['id', 'revision', 'current']


def lock_template(pk, data):
    obj = get_object_or_404(Template.objects.select_for_update(), pk=pk)
    if data.get('revision') != obj.revision:
        raise Conflict()
    return obj


def publish(obj, actor):
    if not obj.draft or not obj.draft.get('pages'):
        raise ValidationError('至少需要一页')
    snap = deepcopy(obj.draft)
    manifest = snap['manifest']
    manifest.update(templateBookID=str(obj.id), title=obj.title, seriesID=obj.series.slug,
                    packageVersion=(obj.versions.order_by('-number').values_list('number', flat=True).first() or 0) + 1)
    obj.current = Version.objects.create(template=obj, number=manifest['packageVersion'], snapshot=snap, actor=actor)
    obj.draft = snap
    obj.revision += 1
    obj.save()
    Event.objects.create(actor=actor, template=obj, action='publish', detail={'version': obj.current.number})


def preview(key):
    return storage.sign(key) if key else None


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


class TemplateAdmin(viewsets.ModelViewSet):
    permission_classes = [PresetAdmin]
    serializer_class = TemplateSerializer
    queryset = Template.objects.select_related('series', 'current').all()
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('series'):
            qs = qs.filter(series_id=self.request.query_params['series'])
        return qs

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
            return Response(dict(revision=obj.revision, pages=[dict(id=p['data']['id'], title=p['data']['title'],
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
            obj.revision += 1
            obj.save()
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def publish(self, request, pk=None):
        obj = lock_template(pk, request.data)
        publish(obj, request.user)
        return Response(self.get_serializer(obj).data)

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
        return Response({'status': obj.status}, status=202)

    def create(self, request):
        ser = UploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        obj = get_object_or_404(Template, pk=data.pop('template'))
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
        return Response(dict(id=str(obj.id), status=obj.status), status=202)


class ProcessorPermission(BasePermission):
    def has_permission(self, request, view):
        expected = settings.DIARY_PRESETS_PROCESSOR_TOKEN
        return bool(expected and secrets.compare_digest(request.headers.get('X-Preset-Processor', ''), expected))


class Processor(APIView):
    """Poll from a dedicated OSS-region worker, never run it on the API host."""
    authentication_classes = []
    permission_classes = [ProcessorPermission]

    @transaction.atomic
    def post(self, request):
        if request.data.get('action') == 'claim':
            # A failed lease is reclaimable. Late result cannot supersede a new lease.
            from django.db.models import Q
            obj = Upload.objects.select_for_update().filter(
                Q(status='queued') | Q(status='processing', lease_until__lt=timezone.now())).order_by('created_at').first()
            if not obj:
                return Response(status=204)
            obj.status = 'processing'
            obj.lease = uuid.uuid4()
            obj.lease_until = timezone.now() + timedelta(minutes=30)
            obj.save()
            return Response(dict(id=str(obj.id), lease=str(obj.lease), object_key=obj.object_key, size=obj.size, mode=obj.mode))
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
                template.draft = merge(template.draft, result, obj.after_page) if obj.mode == 'page' else result
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
        for template in Template.objects.filter(active=True, series__active=True, current__isnull=False).select_related('current', 'series')[:500]:
            snap = template.current.snapshot
            cover = next(p for p in snap['pages'] if p['data']['id'] == snap['manifest']['coverPageID'])
            rows.append(dict(id=str(template.id), title=template.title, series=template.series.slug,
                version=template.current.number, page_count=len(snap['pages']),
                cover_url=preview(snap['keys'][cover['data']['preview']['thumbnailPath']])))
        return Response(dict(series=list(Series.objects.filter(active=True).values('slug', 'title')), books=rows))


class Detail(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, number):
        version = get_object_or_404(Version, template_id=pk, number=number, template__active=True, template__series__active=True)
        snap = version.snapshot
        return Response(dict(manifest=snap['manifest'], page_data=[p['data'] for p in snap['pages']], pages=[dict(id=p['data']['id'], title=p['data']['title'],
            thumbnail_url=preview(snap['keys'][p['data']['preview']['thumbnailPath']]),
            preview_url=preview(snap['keys'][p['data']['preview']['largePath']])) for p in snap['pages']]))

    def post(self, request, pk, number):
        version = get_object_or_404(Version, template_id=pk, number=number, template__active=True, template__series__active=True)
        ids = request.data.get('page_ids')
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
        plan = get_object_or_404(DownloadPlan, pk=pk, owner=request.user, expires_at__gt=timezone.now())
        paths = request.data.get('paths', [])
        if not isinstance(paths, list) or not 1 <= len(paths) <= 50 or any(not isinstance(p, str) or p not in plan.snapshot['keys'] for p in paths):
            raise ValidationError('Invalid resource selection')
        return Response({p: storage.sign(plan.snapshot['keys'][p]) for p in paths})
