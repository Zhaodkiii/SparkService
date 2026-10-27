"""Successful client imports. Book events deliberately have no page records."""
import hashlib
import json
from datetime import timezone as datetime_timezone
from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .admin_support import Conflict
from .models import PresetImportEvent, PresetImportItem, PresetStatisticsState, Version


class ImportPageSerializer(serializers.Serializer):
    source_page_id = serializers.CharField(max_length=200, trim_whitespace=False)
    target_page_id = serializers.UUIDField()


class ImportSerializer(serializers.Serializer):
    operation_id = serializers.UUIDField()
    template_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    mode = serializers.ChoiceField(choices=['book', 'selection'])
    target_book_id = serializers.UUIDField()
    completed_at = serializers.DateTimeField()
    pages = ImportPageSerializer(many=True, required=False, allow_empty=False, max_length=2000)

    def validate(self, data):
        if data['mode'] == 'book' and 'pages' in data:
            raise serializers.ValidationError('整本事件不能携带 pages')
        if data['mode'] == 'selection':
            pages = data.get('pages', [])
            if not pages:
                raise serializers.ValidationError('选页事件必须包含页面明细')
            for key in ('source_page_id', 'target_page_id'):
                if len({p[key] for p in pages}) != len(pages):
                    raise serializers.ValidationError('页面明细不能重复')
            data['pages'] = sorted(pages, key=lambda p: p['source_page_id'])
        data['completed_at'] = data['completed_at'].astimezone(datetime_timezone.utc)
        return data


class ImportEvents(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        expected_owner = request.headers.get('X-Preset-Import-Owner')
        if expected_owner is not None and expected_owner != str(request.user.pk):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('添加事件所属账号与当前会话不一致')
        serializer = ImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        digest = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        identity = dict(user=request.user, operation_id=data['operation_id'])

        def duplicate(event):
            if event.payload_digest != digest:
                raise Conflict('同一添加操作的内容不一致')
            return Response({'operation_id': str(event.operation_id), 'duplicate': True})

        existing = PresetImportEvent.objects.filter(**identity).first()
        if existing:
            return duplicate(existing)
        version = get_object_or_404(Version.objects.select_related('template'),
                                    template_id=data['template_id'], number=data['version'])
        template = version.template
        # Published historical public versions remain reportable after ordinary archival.
        if template.audience == 'private':
            from diary_customizations.models import Delivery
            if template.owner_id != request.user.pk or not Delivery.objects.filter(
                version=version, status='delivered', request__owner=request.user,
                request__deleted_at__isnull=True).exists():
                from rest_framework.exceptions import NotFound
                raise NotFound()
        pages = data.get('pages', [])
        if data['mode'] == 'selection':
            valid_ids = {p['id'] for p in version.snapshot['manifest']['pages']}
            if any(p['source_page_id'] not in valid_ids for p in pages):
                raise serializers.ValidationError('页面不属于所指定的版本')
        try:
            with transaction.atomic():
                event = PresetImportEvent.objects.create(**identity, template=template, version=version,
                    mode=data['mode'], target_book_id=data['target_book_id'],
                    completed_at=data['completed_at'], payload_digest=digest)
                PresetImportItem.objects.bulk_create([
                    PresetImportItem(event=event, **page) for page in pages])
        except IntegrityError:
            existing = PresetImportEvent.objects.filter(**identity).first()
            if existing is None:
                raise
            return duplicate(existing)
        return Response({'operation_id': str(event.operation_id), 'duplicate': False}, status=201)


def statistics_metadata():
    state = PresetStatisticsState.objects.filter(pk=1).first()
    return {'started_at': state.started_at.isoformat() if state else None,
            'scope': 'reported_clients', 'historical': 'not_collected'}


def template_statistics(ids):
    """Two grouped queries, independent of the number of templates or pages."""
    result = {str(pk): dict(book_count=0, selection_count=0, selected_page_count=0, user_count=0) for pk in ids}
    for row in PresetImportEvent.objects.filter(template_id__in=ids).values('template_id').annotate(
        book_count=Count('id', filter=Q(mode='book')),
        selection_count=Count('id', filter=Q(mode='selection')), user_count=Count('user_id', distinct=True)):
        result[str(row.pop('template_id'))].update(row)
    for row in PresetImportItem.objects.filter(event__template_id__in=ids, event__mode='selection').values(
        'event__template_id').annotate(selected_page_count=Count('id')):
        result[str(row['event__template_id'])]['selected_page_count'] = row['selected_page_count']
    return result


def page_statistics(template, number=None):
    qs = PresetImportItem.objects.filter(event__template=template, event__mode='selection')
    if number is not None:
        qs = qs.filter(event__version__number=number)
    return dict(qs.values('source_page_id').annotate(count=Count('id')).values_list('source_page_id', 'count'))
