"""Paginated admin content discovery, including content without a pricing offer."""
import uuid
from django.db.models import Q, Value, CharField, OuterRef, Subquery, Exists
from django.db.models.functions import Cast
from rest_framework import serializers
from .models import ContentOffer, ContentPolicyDraft

class CatalogQuery(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=160, default='')
    target_kind = serializers.ChoiceField(choices=['', 'template', 'sticker_library', 'font'], default='')
    status = serializers.ChoiceField(choices=['', 'unconfigured', 'draft', 'active', 'blocked'], default='')
    access_mode = serializers.ChoiceField(choices=['', 'free', 'pro_only', 'diamond_only', 'pro_or_diamond'], default='')
    availability = serializers.ChoiceField(choices=['', 'available', 'unavailable'], default='')
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)


def content_models():
    from diary_presets.models import Template
    from material_library.models import MaterialLibrary
    from font_library.models import FontFamily
    return {'template': Template, 'sticker_library': MaterialLibrary, 'font': FontFamily}


def public_contents(kind):
    qs = content_models()[kind].objects.all()
    if kind == 'template':
        qs = qs.filter(audience='public',deleted_at__isnull=True)
    elif kind == 'sticker_library':
        qs = qs.filter(Q(template__isnull=True) | Q(template__audience='public'), deleted_at__isnull=True)
    return qs


def available_query(kind):
    result = Q(active=True, current__isnull=False)
    if kind == 'template':
        result &= Q(series__active=True)
    return result


def catalog_page(params):
    form = CatalogQuery(data=params); form.is_valid(raise_exception=True)
    data = form.validated_data
    parts = []
    blocked_ids = None
    if data['status'] == 'blocked':
        from .pricing import publication_checks
        blocked_ids = [d.offer_id for d in ContentPolicyDraft.objects.select_related('offer__current_policy_revision') if publication_checks(d.offer, d.body)]
    for kind in ([data['target_kind']] if data['target_kind'] else content_models()):
        qs = public_contents(kind)
        if data['q']:
            search = Q(title__icontains=data['q'])
            try: search |= Q(pk=uuid.UUID(data['q']))
            except ValueError: pass
            qs = qs.filter(search)
        offers = ContentOffer.objects.filter(target_kind=kind, target_id=OuterRef('pk'))
        qs = qs.annotate(offer_key=Subquery(offers.values('id')[:1]),
                         policy_key=Subquery(offers.values('current_policy_revision_id')[:1]),
                         policy_mode=Subquery(offers.values('current_policy_revision__access_mode')[:1]),
                         has_draft=Exists(ContentPolicyDraft.objects.filter(offer__target_kind=kind, offer__target_id=OuterRef('pk'))))
        if data['status'] == 'unconfigured': qs = qs.filter(policy_key__isnull=True, has_draft=False)
        elif data['status'] == 'draft': qs = qs.filter(has_draft=True)
        elif data['status'] == 'active': qs = qs.filter(policy_key__isnull=False, has_draft=False)
        if blocked_ids is not None: qs = qs.filter(offer_key__in=blocked_ids)
        if data['access_mode']: qs = qs.filter(policy_mode=data['access_mode'])
        if data['availability'] == 'available': qs = qs.filter(available_query(kind))
        elif data['availability'] == 'unavailable': qs = qs.exclude(available_query(kind))
        parts.append(qs.order_by().annotate(target_kind=Value(kind, output_field=CharField()), target_key=Cast('pk', CharField())).values('target_kind', 'target_key', 'title'))
    combined = parts[0].union(*parts[1:], all=True).order_by('title', 'target_kind', 'target_key') if len(parts)>1 else parts[0].order_by('title', 'target_key')
    total = combined.count()
    page = min(data['page'], max(1, (total + data['page_size'] - 1)//data['page_size']))
    start = (page-1)*data['page_size']
    rows = list(combined[start:start+data['page_size']])
    offers = {(x.target_kind, str(x.target_id)): x for x in ContentOffer.objects.filter(target_id__in=[r['target_key'] for r in rows]).select_related('current_policy_revision__published_by', 'contentpolicydraft__actor')}
    objects = {kind: public_contents(kind).select_related('current').in_bulk([r['target_key'] for r in rows if r['target_kind']==kind]) for kind in content_models()}
    from .manage import offer_json
    result = []
    for row in rows:
        kind = row['target_kind']; target = objects[kind][uuid.UUID(row['target_key'])]
        offer = offers.get((kind, str(target.pk)))
        item = offer_json(offer) if offer else dict(id=None, revision=0, access_mode=None, diamond_price=None, bundled_grants=[], terms_version='content-personal-v1', draft=None, workflow_status='unconfigured')
        item.update(target_kind=kind, target_id=str(target.pk), title=target.title, **content_metadata(kind, target))
        result.append(item)
    from django.conf import settings
    return dict(items=result, total=total, page=page, page_size=data['page_size'], test_policy_changes_enabled=settings.BILLING_TEST_POLICY_CHANGES_ENABLED)


def content_metadata(kind, target):
    available = bool(target.active and target.current_id)
    if kind == 'template': available = available and target.series.active
    cover = None
    # Preview failures must not prevent operators from finding/fixing content.
    try:
        if kind == 'template':
            from diary_presets.admin_support import preview
            content = target.current.snapshot if target.current_id else target.draft
            cover_id = content.get('manifest', {}).get('coverPageID')
            page = next((p for p in content.get('pages', []) if p.get('data', {}).get('id') == cover_id), None)
            key = content.get('keys', {}).get(page['data']['preview']['thumbnailPath']) if page else None
            if key: cover = preview(key)
        elif kind == 'font':
            from font_library.models import FontAsset
            from font_library.storage import sign
            content = target.current.content if target.current_id else {}
            asset = FontAsset.objects.filter(pk=content['cover'], family=target).first() if content.get('cover') else None
            if asset: cover = sign(asset.object_key)
        else:
            from material_library.models import ResourceBlob
            from material_library.views import sign
            content = target.current.content if target.current_id else {}
            blob = ResourceBlob.objects.filter(pk=content['cover']).first() if content.get('cover') else None
            if blob: cover = sign(blob.object_key)
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Content cover unavailable: %s %s', kind, target.pk)
        cover = None
    path = '/content/templates' if kind=='template' else '/content/fonts' if kind=='font' else '/content/backgrounds' if target.library_type=='background' else '/content/stickers'
    return dict(cover_url=cover, available=available, content_state='available' if available else 'unpublished' if not target.current_id else 'unavailable', content_path=path)
