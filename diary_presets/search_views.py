from copy import deepcopy
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from .models import SearchTaxon, Template, Event
from .reading_units import suggest, validate, exclusion_reason
from .search import run_search, bump, index_version, validate_taxonomy, normalize
from .admin_support import PresetAdmin, lock_template, preview


class Search(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(run_search(request.query_params, request.user.pk))


class Taxonomy(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import SearchState
        return Response({'revision': SearchState.objects.filter(id=1).values_list('revision', flat=True).first() or 1,
                         'terms': list(SearchTaxon.objects.filter(active=True).order_by('dimension', 'name').values('id', 'dimension', 'name', 'aliases', 'parent_id'))})


class TaxonSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchTaxon
        fields = ['id', 'dimension', 'name', 'aliases', 'parent', 'active', 'merged_into']
        read_only_fields = ['merged_into']

    def validate(self, attrs):
        if self.instance and self.instance.merged_into_id:
            raise ValidationError('词项已合并，请编辑目标词项')
        parent = attrs.get('parent', getattr(self.instance, 'parent', None))
        dimension = attrs.get('dimension', getattr(self.instance, 'dimension', None))
        key = self.instance.pk if self.instance else attrs.get('id')
        if self.instance and ('id' in attrs and attrs['id'] != key or dimension != self.instance.dimension):
            raise ValidationError('已创建词项的身份和维度不可修改')
        seen = {key}
        while parent:
            if dimension != 'location' or parent.dimension != 'location' or parent.pk in seen:
                raise ValidationError('地点父级无效或形成循环')
            seen.add(parent.pk); parent = parent.parent
        aliases = attrs.get('aliases', getattr(self.instance, 'aliases', []))
        if not isinstance(aliases, list) or len(aliases) > 30 or any(not isinstance(v, str) or not v.strip() or len(v) > 120 for v in aliases):
            raise ValidationError('别名需为最多 30 项的字符串数组')
        name = attrs.get('name', getattr(self.instance, 'name', ''))
        own = {normalize(v) for v in [name, *aliases]}
        if len(own) != len(aliases) + 1:
            raise ValidationError('名称和别名重复')
        for term in SearchTaxon.objects.filter(dimension=dimension, merged_into__isnull=True).exclude(pk=key):
            if own.intersection(normalize(v) for v in [term.name, *term.aliases]):
                raise ValidationError('名称或别名已属于同维度的其他词项')
        return attrs


class TaxonAdmin(viewsets.ModelViewSet):
    permission_classes = [PresetAdmin]
    queryset = SearchTaxon.objects.all().order_by('dimension', 'name')
    serializer_class = TaxonSerializer
    pagination_class = None
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def perform_create(self, serializer):
        with transaction.atomic():
            serializer.save(); bump()

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.save()
            for obj in Template.objects.filter(audience='public', current__isnull=False).select_related('current', 'series'):
                index_version(obj, obj.current)
            bump()

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def merge(self, request, pk=None):
        source = get_object_or_404(SearchTaxon.objects.select_for_update(), pk=pk, merged_into__isnull=True)
        target = get_object_or_404(SearchTaxon.objects.select_for_update(), pk=request.data.get('target_id'), merged_into__isnull=True, active=True)
        if source.id == target.id or source.dimension != target.dimension:
            raise ValidationError('只能合并同维度的两个不同词项')
        # A location cannot merge into a descendant: that would create a self ancestor.
        parent, seen = target, set()
        while parent:
            if parent.id == source.id or parent.id in seen:
                raise ValidationError('地点合并形成父级循环')
            seen.add(parent.id); parent = parent.parent
        aliases = list(dict.fromkeys(target.aliases + [source.name] + source.aliases))
        if len(aliases) > 30: raise ValidationError('合并后别名超过 30 项，请先整理')
        target.aliases = aliases; target.save(update_fields=['aliases'])
        source.merged_into = target; source.active = False; source.save(update_fields=['merged_into', 'active'])
        SearchTaxon.objects.filter(merged_into=source).update(merged_into=target)
        SearchTaxon.objects.filter(parent=source).update(parent=target)
        for obj in Template.objects.filter(audience='public', current__isnull=False).select_related('current', 'series'):
            index_version(obj, obj.current)
        bump()
        return Response(self.get_serializer(target).data)


class ReadingUnitAdmin(viewsets.ViewSet):
    permission_classes = [PresetAdmin]

    def list(self, request):
        rows = []
        qs = Template.objects.filter(audience='public').select_related('series')
        if request.query_params.get('template'):
            qs = qs.filter(id=request.query_params['template'])
        if request.query_params.get('series'):
            qs = qs.filter(series__slug=request.query_params['series'])
        for obj in qs:
            manifest = obj.draft.get('manifest')
            if not manifest: continue
            for unit in manifest.get('readingUnits', []):
                row = dict(unit, template_id=str(obj.id), book_title=obj.title, revision=obj.revision,
                           series=obj.series.slug,
                           exclusion_reason=exclusion_reason(manifest, unit))
                if request.query_params.get('q') and normalize(request.query_params['q']) not in normalize(str([unit['title'], unit.get('searchKeywords', []), unit.get('tagIDs', [])])):
                    continue
                rows.append(row)
        return Response(rows)

    @action(detail=False, methods=['post'], url_path='batch-search-metadata')
    def batch(self, request):
        groups = request.data.get('templates', [])
        if not isinstance(groups, list) or not 1 <= len(groups) <= 50:
            raise ValidationError('需明确选择 1–50 本模板')
        field = request.data.get('field')
        operation = request.data.get('operation')
        values = request.data.get('values')
        if field not in ('tagIDs', 'searchKeywords', 'locationIDs') or operation not in ('add', 'remove', 'replace') or not isinstance(values, list):
            raise ValidationError('批量操作无效')
        results = []
        for group in groups:
            try:
                with transaction.atomic():
                    obj = lock_template(group['template_id'], group)
                    selected = set(group['unit_ids'])
                    manifest = obj.draft['manifest']
                    if not selected or not selected <= {u['id'] for u in manifest.get('readingUnits', [])}:
                        raise ValidationError('未选择有效跨页')
                    for unit in manifest['readingUnits']:
                        if unit['id'] not in selected: continue
                        old = unit.get(field, [])
                        unit[field] = list(dict.fromkeys(old + values)) if operation == 'add' else [v for v in old if v not in values] if operation == 'remove' else values
                        if field == 'locationIDs': unit['locationMode'] = 'explicit'
                    validate(manifest); validate_taxonomy(manifest)
                    obj.revision += 1; obj.save(update_fields=['draft', 'revision'])
                    Event.objects.create(template=obj, actor=request.user, action='search_batch', detail={'field': field, 'operation': operation, 'unit_ids': sorted(selected)})
                    results.append({'template_id': str(obj.id), 'revision': obj.revision, 'ok': True})
            except (ValidationError, ValueError, KeyError) as exc:
                results.append({'template_id': group.get('template_id'), 'ok': False, 'error': str(exc)})
            except Exception as exc:
                from .views import Conflict
                if not isinstance(exc, Conflict): raise
                results.append({'template_id': group.get('template_id'), 'ok': False, 'error': '编辑冲突，请刷新'})
        return Response({'results': results})


class TemplateSearchMixin:
    @action(detail=True, methods=['get', 'patch'], url_path=r'reading-units/(?P<unit_id>[^/.]+)/search-metadata')
    def unit_search_metadata(self, request, pk=None, unit_id=None):
        with transaction.atomic():
            obj = lock_template(pk, request.data) if request.method == 'PATCH' else self.get_object()
            unit = next((u for u in obj.draft.get('manifest', {}).get('readingUnits', []) if u['id'] == unit_id), None)
            if not unit:
                from django.http import Http404
                raise Http404()
            if request.method == 'PATCH':
                before = deepcopy(unit)
                fields = {'title':'title', 'location_mode':'locationMode', 'location_ids':'locationIDs', 'tag_ids':'tagIDs', 'search_keywords':'searchKeywords', 'search_enabled':'searchEnabled'}
                if set(request.data) - set(fields) - {'revision'}: raise ValidationError('包含不可编辑字段')
                for field, target in fields.items():
                    if field in request.data: unit[target] = deepcopy(request.data[field])
                try:
                    validate(obj.draft['manifest']); validate_taxonomy(obj.draft['manifest'])
                except ValueError as exc: raise ValidationError(str(exc))
                obj.revision += 1; obj.save(update_fields=['draft', 'revision'])
                Event.objects.create(template=obj, actor=request.user, action='unit_search_metadata', detail={'before':before,'after':deepcopy(unit)})
            published = next((u for u in (obj.current.snapshot['manifest'].get('readingUnits', []) if obj.current else []) if u['id'] == unit_id), None)
            return Response({'revision':obj.revision, 'unit':unit, 'published':published, 'exclusion_reason':exclusion_reason(obj.draft['manifest'],unit)})

    @action(detail=True, methods=['get', 'put'], url_path='reading-units')
    def reading_units(self, request, pk=None):
        if request.method == 'PUT':
            with transaction.atomic():
                obj = lock_template(pk, request.data)
                if not obj.draft.get('manifest'): raise ValidationError('请先上传页面')
                before = deepcopy(obj.draft['manifest'])
                manifest = obj.draft['manifest']
                for field in ('readingUnits', 'pageMetadata', 'metadata'):
                    if field in request.data: manifest[field] = deepcopy(request.data[field])
                manifest['schemaVersion'] = 2
                try:
                    validate(manifest); validate_taxonomy(manifest)
                except ValueError as exc:
                    raise ValidationError(str(exc))
                obj.revision += 1; obj.save(update_fields=['draft', 'revision'])
                Event.objects.create(template=obj, actor=request.user, action='search_metadata', detail={'before': {k: before.get(k) for k in ('readingUnits', 'pageMetadata', 'metadata')}, 'after': {k: manifest.get(k) for k in ('readingUnits', 'pageMetadata', 'metadata')}})
        else:
            obj = self.get_object()
        manifest = obj.draft.get('manifest', {})
        return Response({'revision': obj.revision, 'manifest': {k: manifest.get(k) for k in ('schemaVersion', 'readingUnits', 'pageMetadata', 'metadata')},
                         'pages': [dict(id=p['data']['id'], title=p['data']['title'], thumbnail=preview(obj.draft['keys'][p['data']['preview']['thumbnailPath']]),
                                        preview=preview(obj.draft['keys'][p['data']['preview']['largePath']])) for p in obj.draft.get('pages', [])],
                         'eligibility': {u['id']: exclusion_reason(manifest, u) for u in manifest.get('readingUnits', [])}})

    @action(detail=True, methods=['post'], url_path='suggest-reading-units')
    @transaction.atomic
    def suggest_reading_units(self, request, pk=None):
        obj = lock_template(pk, request.data)
        if obj.draft.get('manifest', {}).get('readingUnits'):
            raise ValidationError('已有编排，不能覆盖；请在跨页管理中编辑')
        if not obj.draft.get('pages'): raise ValidationError('请先上传页面')
        obj.draft['manifest'] = suggest(obj.draft['manifest'])
        obj.revision += 1; obj.save(update_fields=['draft', 'revision'])
        Event.objects.create(template=obj, actor=request.user, action='suggest_pairing')
        return Response({'revision': obj.revision, 'count': len(obj.draft['manifest']['readingUnits'])})

    @action(detail=True, methods=['post'], url_path='search-preview')
    def search_preview(self, request, pk=None):
        obj = self.get_object()
        if request.data.get('revision') != obj.revision:
            from .views import Conflict
            raise Conflict()
        try:
            return Response(run_search(request.data, request.user.pk, draft=(obj, obj.draft)))
        except ValueError as exc:
            raise ValidationError(str(exc))

    @action(detail=True, methods=['post'], url_path='discard-search-draft')
    @transaction.atomic
    def discard_search_draft(self, request, pk=None):
        obj = lock_template(pk, request.data)
        if not obj.current: raise ValidationError('暂无已发布版本')
        obj.draft = deepcopy(obj.current.snapshot); obj.revision += 1; obj.save(update_fields=['draft', 'revision'])
        return Response({'revision': obj.revision})
