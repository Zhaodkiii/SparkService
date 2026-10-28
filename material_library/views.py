import unicodedata
from django.db import transaction
from django.db.models import F, Q, Max
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from diary_presets.views import PresetAdmin
from diary_presets.storage import sign as preset_sign, prefix as preset_prefix
from rest_framework.exceptions import PermissionDenied

def sign(key):
    if not key.startswith(preset_prefix()+"blobs/"):
        raise PermissionDenied("私人资源不能通过公共素材库访问")
    return preset_sign(key)
from .models import *
from .catalog import CATEGORIES, ALIASES
from .services import revision, publish_library


def visible():
    return MaterialLibrary.objects.filter(Q(template__isnull=True) | Q(template__audience='public', template__active=True, template__series__active=True), active=True, current__isnull=False)


def library_json(lib, user):
    return dict(id=str(lib.pk), template_id=str(lib.template_id), title=lib.title, type=lib.library_type,
                series=lib.template.series.title, version=lib.current.number if lib.current_id else 0,
                count=lib.current.items.count() if lib.current_id else 0,
                favorite_count=lib.favorites.count(), is_favorited=lib.favorites.filter(user=user).exists())


def item_json(item, user):
    r = item.revision
    return dict(id=str(r.material_id), revision=r.pk, name=r.name, kind=r.kind, subcategory=r.subcategory,
                keywords=r.keywords, aliases=r.aliases, sources=r.sources,
                thumbnail_url=sign(r.thumbnail.object_key), thumbnail_sha256=r.thumbnail_id, sha256=r.resource_id, byte_size=r.resource.byte_size,
                width=r.resource.width, height=r.resource.height,
                favorite_count=r.material.favorites.count(), is_favorited=r.material.favorites.filter(user=user).exists())


class AuthView(APIView):
    permission_classes = [IsAuthenticated]


class Categories(AuthView):
    def get(self, request):
        result=[]
        for kind,(title,defaults) in CATEGORIES.items():
            subs=dict(defaults)
            for row in MaterialCategory.objects.filter(kind=kind).order_by('position','subcategory'):
                if row.active: subs[row.subcategory]=row.title
                else: subs.pop(row.subcategory,None)
            result.append(dict(kind=kind,title=title,subcategories=[dict(id=k,title=v) for k,v in subs.items()]))
        return Response(result)


class Libraries(AuthView):
    def get(self, request):
        if request.query_params.get('schema') == '2':
            from .catalog_v2 import LibrariesV2
            return LibrariesV2().get(request)
        qs = visible().filter(template__isnull=False).select_related('template__series', 'current').order_by('template__position', 'id')
        for key, field in [('type','library_type'), ('template','template_id'), ('series','template__series__slug')]:
            if value := request.query_params.get(key):
                if key == 'template': value = serializers.UUIDField().run_validation(value)
                qs = qs.filter(**{field:value})
        if request.query_params.get('favorites') == '1': qs = qs.filter(favorites__user=request.user)
        libraries = list(qs[:200])
        if number := request.query_params.get('template_version'):
            try: number = int(number)
            except ValueError: raise ValidationError('模板版本无效')
            for lib in libraries:
                binding = TemplateLibraryBinding.objects.filter(preset_version__template_id=lib.template_id, preset_version__number=number, library_type=lib.library_type).select_related('library_version').first()
                lib.current = binding.library_version if binding else lib.versions.filter(preset_version__number=number).order_by('-number').first()
            libraries = [lib for lib in libraries if lib.current is not None]
        return Response([library_json(lib, request.user) for lib in libraries])


class Items(AuthView):
    def get(self, request, pk=None):
        if request.query_params.get('schema') == '2':
            from .catalog_v2 import ItemsV2
            return ItemsV2().get(request, pk)
        lib = get_object_or_404(visible(), pk=pk) if pk else None
        try:
            number = int(request.query_params.get('version', lib.current.number if lib else 0))
            after = int(request.query_params.get('after', 0))
        except (TypeError, ValueError): raise ValidationError('无效分页或版本')
        if after < 0 or number < 0: raise ValidationError('无效分页或版本')
        if lib:
            version = get_object_or_404(lib.versions, number=number)
            qs = version.items.all()
        else:
            qs = LibraryItem.objects.filter(version__library__in=visible(), version_id=F('version__library__current_id'))
            if typ := request.query_params.get('type'): qs = qs.filter(material__material_type=typ)
            if request.query_params.get('scope') == 'libraries': qs = qs.filter(version__library__favorites__user=request.user)
            if template := request.query_params.get('template'): qs = qs.filter(version__library__template_id=serializers.UUIDField().run_validation(template))
            if ids := request.query_params.get('template_ids'):
                ids = [serializers.UUIDField().run_validation(v) for v in ids.split(',')[:100]]
                qs = qs.filter(version__library__template_id__in=ids)
            if series := request.query_params.get('series'): qs = qs.filter(version__library__template__series__slug=series)
        if not lib and request.query_params.get('template_version') and request.query_params.get('template'):
            binding = TemplateLibraryBinding.objects.filter(preset_version__template_id=request.query_params['template'],preset_version__number=request.query_params['template_version'],library_type=request.query_params.get('type','sticker')).first()
            if binding:
                qs = LibraryItem.objects.filter(version_id=binding.library_version_id,version__library__in=visible())
            else:
                qs = LibraryItem.objects.none()
        qs = qs.filter(material__active=True).select_related('revision__resource','revision__thumbnail','revision__material').order_by('id')
        # IDs are assigned in position order at publication and immutable thereafter.
        if request.query_params.get('favorites') == '1': qs = qs.filter(material__favorites__user=request.user)
        for key in ('kind', 'subcategory'):
            if value := request.query_params.get(key): qs = qs.filter(**{'revision__'+key:value})
        query = unicodedata.normalize('NFKC', request.query_params.get('q','')).strip()[:120]
        for term in query.split()[:10]:
            normalized = ALIASES.get(term, term)
            match = Q()
            for token in {term, normalized}:
                match |= Q(revision__name__icontains=token) | Q(revision__keywords__icontains=token) | Q(revision__aliases__icontains=token)
                match |= Q(version__library__template__title__icontains=token) | Q(version__library__template__series__title__icontains=token)
                for kind, (label, subs) in CATEGORIES.items():
                    if token in label: match |= Q(revision__kind=kind)
                    for sub, title in subs.items():
                        if token in title: match |= Q(revision__kind=kind, revision__subcategory=sub)
            qs = qs.filter(match)
        if not lib:
            ids = qs.order_by().values('material_id').annotate(last_id=Max('id')).values('last_id')
            qs = qs.filter(id__in=ids)
        rows = list(qs.filter(id__gt=after)[:41])
        return Response(dict(version=number, items=[item_json(i,request.user) for i in rows[:40]], next=rows[39].pk if len(rows)>40 else None))


class Favorite(AuthView):
    def post(self, request, target, pk):
        if not isinstance(request.data.get('favorite'), bool): raise ValidationError('favorite 必须为布尔值')
        if target not in ('libraries', 'items'): raise ValidationError('无效收藏类型')
        if target == 'libraries':
            obj = get_object_or_404(MaterialLibrary.objects.filter(Q(template__isnull=True) | Q(template__audience='public')), pk=pk)
            model, field = LibraryFavorite, 'library'
            if request.data['favorite'] and not visible().filter(pk=pk).exists(): raise ValidationError('素材库不可用')
        else:
            obj = get_object_or_404(Material.objects.filter(Q(libraryitem__version__library__template__isnull=True) | Q(libraryitem__version__library__template__audience='public')).distinct(), pk=pk)
            model, field = MaterialFavorite, 'material'
            if request.data['favorite'] and (not obj.active or not LibraryItem.objects.filter(material=obj, version__library__in=visible(), version_id=F('version__library__current_id')).exists()):
                raise ValidationError('素材不可用')
        lookup = dict(user=request.user, **{field:obj})
        if request.data['favorite']: model.objects.get_or_create(**lookup)
        else: model.objects.filter(**lookup).delete()
        return Response(dict(is_favorited=model.objects.filter(**lookup).exists(), favorite_count=model.objects.filter(**{field:obj}).count()))


class Download(AuthView):
    def post(self, request, pk):
        qs = LibraryItem.objects.select_related('revision__resource').filter(revision_id=pk,
            material__active=True, version__library__in=visible())
        if request.data.get('library_id'):
            qs = qs.filter(version__library_id=serializers.UUIDField().run_validation(request.data['library_id']), version__number=serializers.IntegerField(min_value=1).run_validation(request.data.get('library_version')))
        else:
            qs = qs.filter(version_id=F('version__library__current_id'))
        item = qs.first()
        if item is None: raise ValidationError('素材不可用，请刷新目录')
        from billing.access import require_content
        require_content(request, 'sticker_library', item.version.library_id)
        r = item.revision.resource
        result = dict(url=sign(r.object_key), sha256=r.pk, byte_size=r.byte_size)
        if request.query_params.get('schema') == '2':
            from django.utils import timezone
            from datetime import timedelta
            result.update(revision=pk, resource_id=r.pk, mime=r.mime, width=r.width, height=r.height,
                          expires_at=(timezone.now()+timedelta(minutes=15)).isoformat())
        return Response(result)


class Manage(AuthView):
    permission_classes = [PresetAdmin]

    def get(self, request, template):
        libs = MaterialLibrary.objects.filter(template_id=template).select_related('template__series','current')
        return Response([dict(**library_json(lib,request.user), items=[item_json(i,request.user) for i in lib.current.items.select_related('revision__resource','revision__thumbnail','revision__material')] if lib.current_id else []) for lib in libs])

    @transaction.atomic
    def post(self, request, template):
        lib = get_object_or_404(MaterialLibrary, pk=serializers.UUIDField().run_validation(request.data.get('library')), template_id=template)
        entries = request.data.get('items')
        if not isinstance(entries, list) or len(entries)>2000: raise ValidationError('无效素材列表')
        revisions = []
        for entry in entries:
            if not isinstance(entry, dict): raise ValidationError('无效素材条目')
            r = get_object_or_404(MaterialRevision, pk=serializers.IntegerField(min_value=1).run_validation(entry.get('revision')))
            data = dict(name=entry.get('name',r.name), kind=entry.get('kind',r.kind), subcategory=entry.get('subcategory',r.subcategory),
                        keywords=entry.get('keywords',r.keywords), aliases=entry.get('aliases',r.aliases),
                        resource_id=r.resource_id, thumbnail_id=r.thumbnail_id, sources=r.sources)
            try: revisions.append(revision(r.material, data))
            except ValueError as e: raise ValidationError(str(e))
        result = publish_library(lib,revisions,request.data.get('version'))
        return Response(dict(version=result.number))

class Available(Items):
    permission_classes = [PresetAdmin]
