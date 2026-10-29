"""Versioned material catalog. JSON control plane; images are signed OSS objects."""
import hashlib
import json
import uuid
from datetime import timedelta
from django.core import signing
from django.core.cache import cache
from django.db.models import F, Q, Case, When, Value, IntegerField
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework import serializers
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from .models import *
from .views import AuthView, visible, item_json, sign


class Conflict(APIException):
    status_code = 409
    default_detail = '内容已更新，请重新加载后重试'


class Gone(APIException):
    status_code = 410
    default_detail = '内容已下架或分页已过期，请刷新'


def public_libraries(include_deleted=False):
    qs = MaterialLibrary.objects.filter(Q(template__isnull=True) | Q(template__audience='public'))
    return qs if include_deleted else qs.filter(deleted_at__isnull=True)


def blob_json(blob):
    return dict(resource_id=blob.pk, sha256=blob.pk, url=sign(blob.object_key),
                width=blob.width, height=blob.height, byte_size=blob.byte_size,
                expires_at=(timezone.now()+timedelta(minutes=15)).isoformat())


def library_json(lib, user, version=None):
    version = version or lib.current
    content = version.content if version else {}
    cover = ResourceBlob.objects.filter(pk=content.get('cover')).first()
    previews = {b.pk: b for b in ResourceBlob.objects.filter(pk__in=content.get('previews', []))}
    available = visible().filter(pk=lib.pk).exists()
    return dict(id=str(lib.pk), template_id=str(lib.template_id) if lib.template_id else None,
        origin_type='template' if lib.template_id else 'independent', type=lib.library_type,
        title=content.get('title', lib.title), description=content.get('description', ''),
        series=lib.template.series.title if lib.template_id else '',
        version=version.number if version else 0, availability='published' if available else 'unavailable',
        count=version.items.filter(material__active=True).count() if version else 0,
        tags=content.get('tags', []), cover=blob_json(cover) if cover and available else None,
        previews=[blob_json(previews[k]) for k in content.get('previews', []) if k in previews] if available else [],
        favorite_count=lib.favorites.count(), is_favorited=lib.favorites.filter(user=user).exists(),
        active=lib.active, first_published_at=lib.first_published_at, new_until=lib.new_until, state_revision=lib.state_revision, featured=lib.featured, sort_order=lib.sort_order)


def item_data(row, user):
    result = item_json(row, user)
    result.update(library_id=str(row.version.library_id), library_version=row.version.number, availability='published')
    return result


def paginate(request, rows, serialize, identity):
    """Snapshot row IDs, bound to account, filters, endpoint; no signed URLs in cache."""
    params = sorted((k, v) for k, v in request.query_params.items() if k not in ('cursor',))
    binding = hashlib.sha256(json.dumps([str(request.user.pk), identity, params]).encode()).hexdigest()
    cursor = request.query_params.get('cursor')
    try:
        limit = int(request.query_params.get('limit', 30))
        if not 1 <= limit <= 100: raise ValueError()
    except ValueError: raise ValidationError('limit 必须为 1—100')
    if cursor:
        try: token = signing.loads(cursor, salt='materials-cursor', max_age=1800)
        except signing.BadSignature: raise Gone()
        if token.get('binding') != binding: raise ValidationError('游标不属于当前查询')
        ids = cache.get('materials-snapshot:'+token['id'])
        if ids is None: raise Gone()
        offset = token['offset']; snapshot = token['id']
    else:
        ids = [dict(id=str(row.pk),version_id=row.current_id) for row in rows] if identity == 'libraries' else [dict(id=str(row.pk)) for row in rows]
        snapshot = uuid.uuid4().hex; offset = 0
        cache.set('materials-snapshot:'+snapshot, ids, 1800)
    records = ids[offset:offset+limit]
    selected = [r['id'] for r in records]
    # Re-evaluate visibility on each page, including after a takedown.
    if identity.startswith('items:') and cursor:
        snapshot_rows = LibraryItem.objects.filter(pk__in=selected).filter(Q(material__active=True, version__library__in=visible()) | Q(material__favorites__user=request.user, version__library__in=public_libraries())).distinct().select_related('version','revision__resource','revision__thumbnail','revision__material')
        index = {str(r.pk):r for r in snapshot_rows}
    else:
        index = {str(r.pk): r for r in rows.filter(pk__in=selected)} if hasattr(rows, 'filter') else {str(r.pk):r for r in rows}
    if identity == 'libraries':
        versions={v.pk:v for v in LibraryVersion.objects.filter(pk__in=[r['version_id'] for r in records if r.get('version_id')])}
        for record in records:
            if record['id'] in index and record.get('version_id') in versions:
                index[record['id']].current=versions[record['version_id']]
    result = [serialize(index[pk]) for pk in selected if pk in index]
    next_offset = offset + limit
    next_cursor = signing.dumps(dict(id=snapshot, offset=next_offset, binding=binding), salt='materials-cursor') if next_offset < len(ids) else None
    return dict(items=result, next_cursor=next_cursor, snapshot_token=snapshot)


def positive_version(value):
    return serializers.IntegerField(min_value=1).run_validation(value)


def validate_filters(request):
    if request.query_params.get('type') not in (None,'','sticker','background'):raise ValidationError('无效素材类型')
    from .catalog import CATEGORIES
    if request.query_params.get('kind') not in (None,'',*CATEGORIES.keys()):raise ValidationError('无效分类')
    if request.query_params.get('favorites') not in (None,'0','1'):raise ValidationError('无效收藏筛选')


def query_terms(request):
    q = request.query_params.get('q', '').strip()
    if len(q) > 100: raise ValidationError('搜索词最多 100 字')
    return q.split()


class LibrariesV2(AuthView):
    def get(self, request):
        validate_filters(request)
        mine = request.query_params.get('favorites') == '1'
        qs = public_libraries().filter(favorites__user=request.user) if mine else visible()
        qs = qs.select_related('template__series', 'current')
        if typ := request.query_params.get('type'): qs = qs.filter(library_type=typ)
        template = request.query_params.get('template')
        requested_version = request.query_params.get('template_version')
        bound_versions = {}
        if template:
            template = serializers.UUIDField().run_validation(template)
            from diary_presets.models import Template
            book = get_object_or_404(Template, pk=template, audience='public', active=True, series__active=True)
            version_number = positive_version(requested_version) if requested_version else (book.current.number if book.current_id else None)
            bindings = TemplateLibraryBinding.objects.filter(preset_version__template=book, preset_version__number=version_number)
            bound_versions = {b.library_version.library_id: b.library_version for b in bindings.select_related('library_version')}
            qs = qs.filter(pk__in=bound_versions)
        elif requested_version:
            raise ValidationError('template_version 必须同时提供 template')
        terms=query_terms(request)
        for term in terms:
            qs = qs.filter(Q(title__icontains=term) | Q(current__content__description__icontains=term) | Q(current__content__tags__icontains=term))
        if tag := request.query_params.get('tag'): qs = qs.filter(current__content__tags__icontains=tag)
        mode = request.query_params.get('sort', 'recommended')
        if mode not in ('recommended','latest','added'): raise ValidationError('无效排序')
        qs = qs.order_by('-favorites__created_at','id') if mine else qs.order_by('-first_published_at','id') if mode == 'latest' else qs.order_by('-featured','sort_order','id')
        # Legacy libraries remain accessible via template; discover only fully described packs.
        if not mine and not request.query_params.get('template'): qs = qs.exclude(current__content={})
        if terms:
            term=terms[0]
            qs=qs.annotate(search_rank=Case(When(title__iexact=term,then=Value(0)),When(title__istartswith=term,then=Value(1)),default=Value(2),output_field=IntegerField())).order_by('search_rank','id')
        def serialize(lib):
            return library_json(lib, request.user, bound_versions.get(lib.pk))
        return Response(paginate(request, qs, serialize, 'libraries'))


class LibraryDetail(AuthView):
    def get(self, request, pk):
        qs = public_libraries().filter(Q(pk__in=visible()) | Q(favorites__user=request.user)).distinct()
        lib = get_object_or_404(qs.select_related('current','template__series'), pk=pk)
        version = get_object_or_404(lib.versions, number=positive_version(request.query_params['version'])) if request.query_params.get('version') else lib.current
        return Response(library_json(lib,request.user,version))


class ItemsV2(AuthView):
    def get(self, request, pk=None):
        validate_filters(request)
        scope = request.query_params.get('scope','all')
        if scope not in ('all','my','libraries'): raise ValidationError('无效搜索范围')
        if scope == 'my' and (request.query_params.get('favorites') or request.query_params.get('library_id')): raise ValidationError('搜索范围冲突')
        pk = pk or request.query_params.get('library_id')
        if pk: pk=serializers.UUIDField().run_validation(pk)
        qs = LibraryItem.objects.filter(version__library__in=visible(), material__active=True)
        if pk:
            lib = get_object_or_404(visible(), pk=pk)
            number = request.query_params.get('version')
            if not number: raise ValidationError('包查询必须指定 version')
            version = get_object_or_404(lib.versions, number=positive_version(number))
            qs = qs.filter(version=version)
        else:
            qs = qs.filter(version_id=F('version__library__current_id'))
            if scope == 'my': qs = qs.filter(Q(version__library__favorites__user=request.user) | Q(material__favorites__user=request.user))
            elif scope == 'libraries': qs = qs.filter(version__library__favorites__user=request.user)
        if request.query_params.get('favorites') == '1': qs = qs.filter(material__favorites__user=request.user)
        if typ := request.query_params.get('type'): qs = qs.filter(material__material_type=typ)
        for key in ('kind','subcategory'):
            if value := request.query_params.get(key): qs = qs.filter(**{'revision__'+key:value})
        terms=query_terms(request)
        for term in terms:
            qs = qs.filter(Q(revision__name__icontains=term)|Q(revision__aliases__icontains=term)|Q(revision__keywords__icontains=term))
        qs = qs.select_related('version','revision__resource','revision__thumbnail','revision__material').order_by('-revision_id','position','id').distinct()
        if terms:
            term=terms[0]
            qs=qs.annotate(search_rank=Case(When(revision__name__iexact=term,then=Value(0)),When(revision__name__istartswith=term,then=Value(1)),When(revision__aliases__icontains=term,then=Value(2)),default=Value(3),output_field=IntegerField())).order_by('search_rank','material_id','-revision_id','id')
        # Freeze exact membership IDs; only one revision of each material in aggregated results.
        rows=[]; seen=set()
        for row in qs:
            if row.material_id not in seen: rows.append(row); seen.add(row.material_id)
        if not pk and (request.query_params.get('favorites') == '1' or scope == 'my'):
            missing = MaterialFavorite.objects.filter(user=request.user).exclude(material_id__in=seen).values_list('material_id',flat=True)
            unavailable = LibraryItem.objects.filter(material_id__in=missing,version__library__in=public_libraries()).select_related('version','revision__resource','revision__thumbnail','revision__material').order_by('-revision_id')
            for row in unavailable:
                if row.material_id not in seen:
                    if request.query_params.get('type') and row.material.material_type != request.query_params['type']: continue
                    if any(term not in (row.revision.name+' '.join(row.revision.keywords+row.revision.aliases)) for term in query_terms(request)): continue
                    rows.append(row);seen.add(row.material_id)
        if pk and not terms: rows.sort(key=lambda r:(r.position,r.pk))
        def serialize(row):
            if not row.material.active or (not pk and not LibraryItem.objects.filter(material_id=row.material_id,version__library__in=visible(),version_id=F('version__library__current_id')).exists()):
                r=row.revision
                return dict(id=str(r.material_id),revision=r.pk,name=r.name,kind=r.kind,subcategory=r.subcategory,keywords=r.keywords,aliases=r.aliases,thumbnail_sha256=r.thumbnail_id,thumbnail_url='',sha256=r.resource_id,byte_size=r.resource.byte_size,is_favorited=True,favorite_count=r.material.favorites.count(),availability='unavailable')
            return item_data(row,request.user)
        response=paginate(request,rows,serialize,'items:'+str(pk))
        response['library_version']=version.number if pk else None
        response['version']=version.number if pk else 0
        return Response(response)


class ItemDetail(AuthView):
    def get(self,request,pk):
        row=LibraryItem.objects.filter(material_id=pk, material__active=True,version__library__in=visible(),version_id=F('version__library__current_id')).select_related('version','revision__resource','revision__thumbnail','revision__material').order_by('-revision_id').first()
        if row is None: raise Gone()
        return Response(item_data(row,request.user))


class Previews(AuthView):
    parser_classes=[JSONParser]
    def post(self,request):
        entries=request.data.get('resources')
        if not isinstance(entries,list) or len(entries)>50: raise ValidationError('最多 50 项')
        result=[]
        for entry in entries:
            if not isinstance(entry,dict):raise ValidationError('无效资源条目')
            lib=get_object_or_404(visible(),pk=serializers.UUIDField().run_validation(entry.get('library_id')))
            version=get_object_or_404(lib.versions,number=positive_version(entry.get('version')))
            hashes=set(version.content.get('previews',[])+[version.content.get('cover')])
            hashes.update(version.items.filter(material__active=True).values_list('revision__thumbnail_id',flat=True))
            if entry.get('resource_id') not in hashes: raise ValidationError('资源不属于可见版本')
            result.append(blob_json(get_object_or_404(ResourceBlob,pk=entry['resource_id'])))
        return Response(result)


class Tags(AuthView):
    def get(self,request):
        tags=set(MaterialTag.objects.filter(active=True).values_list('title',flat=True))
        disabled=set(MaterialTag.objects.filter(active=False).values_list('title',flat=True))
        for content in visible().values_list('current__content',flat=True):
            tags.update(content.get('tags',[]))
        return Response(sorted(tags-disabled))
