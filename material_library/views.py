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
from diary_presets.storage import sign
from .models import *
from .catalog import CATEGORIES, ALIASES
from .services import revision, publish_library


def visible():
    return MaterialLibrary.objects.filter(active=True, template__active=True, template__series__active=True, current__isnull=False)


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
        return Response([dict(kind=k, title=v[0], subcategories=[dict(id=s, title=t) for s,t in v[1].items()]) for k,v in CATEGORIES.items()])


class Libraries(AuthView):
    def get(self, request):
        qs = visible().select_related('template__series', 'current').order_by('template__position', 'id')
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
                lib.current = lib.versions.filter(preset_version__number=number).order_by('-number').first()
            libraries = [lib for lib in libraries if lib.current is not None]
        return Response([library_json(lib, request.user) for lib in libraries])


class Items(AuthView):
    def get(self, request, pk=None):
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
            obj = get_object_or_404(MaterialLibrary, pk=pk)
            model, field = LibraryFavorite, 'library'
            if request.data['favorite'] and not visible().filter(pk=pk).exists(): raise ValidationError('素材库不可用')
        else:
            obj = get_object_or_404(Material, pk=pk)
            model, field = MaterialFavorite, 'material'
            if request.data['favorite'] and (not obj.active or not LibraryItem.objects.filter(material=obj, version__library__in=visible(), version_id=F('version__library__current_id')).exists()):
                raise ValidationError('素材不可用')
        lookup = dict(user=request.user, **{field:obj})
        if request.data['favorite']: model.objects.get_or_create(**lookup)
        else: model.objects.filter(**lookup).delete()
        return Response(dict(is_favorited=model.objects.filter(**lookup).exists(), favorite_count=model.objects.filter(**{field:obj}).count()))


class Download(AuthView):
    def post(self, request, pk):
        item = LibraryItem.objects.select_related('revision__resource').filter(revision_id=pk,
            material__active=True, version__library__in=visible(), version_id=F('version__library__current_id')).first()
        if item is None: raise ValidationError('素材不可用，请刷新目录')
        r = item.revision.resource
        return Response(dict(url=sign(r.object_key), sha256=r.pk, byte_size=r.byte_size))


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
