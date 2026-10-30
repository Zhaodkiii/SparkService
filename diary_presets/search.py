"""Version-bound search projections. Editable content remains in version snapshots."""
import hashlib
import json
import re
import time
from copy import deepcopy
from django.core import signing
from django.db import transaction
from django.db.models import F, Case, When, Value, IntegerField, Q
from django.db.models.functions import Greatest
from rest_framework.exceptions import ValidationError, APIException
from .models import CatalogEntry, CatalogEntryTerm, SearchTaxon, SearchState, Template, Series
from .reading_units import normalize, clean_title, exclusion_reason, page_ids, validate
from . import storage


class StaleCursor(APIException):
    status_code = 409
    default_detail = {'code': 'SEARCH_CURSOR_STALE', 'detail': '搜索结果已更新，请刷新'}


def bump():
    state, _ = SearchState.objects.get_or_create(id=1)
    SearchState.objects.filter(id=state.id).update(revision=F('revision') + 1)


def taxonomy():
    return {t.id: t for t in SearchTaxon.objects.all()}


def validate_taxonomy(manifest, terms=None):
    terms = taxonomy() if terms is None else terms
    metadata = manifest.get('metadata', {})
    if not isinstance(metadata, dict):
        raise ValueError('本级元数据必须为对象')
    if metadata.get('locationScope', 'mixed') not in {'single_city', 'mixed'}:
        raise ValueError('地点范围无效')
    defaults = metadata.get('defaultLocationIDs', [])
    if not isinstance(defaults, list) or len(defaults) > 30 or any(not isinstance(v, str) for v in defaults):
        raise ValueError('默认地点无效')
    if metadata.get('locationScope') == 'single_city' and len(defaults) > 1:
        raise ValueError('单城市范围只能设置一个默认地点')
    for obj in [metadata] + manifest.get('readingUnits', []) + list(manifest.get('pageMetadata', {}).values()):
        for field, dimension in [('defaultLocationIDs', 'location'), ('locationIDs', 'location'), ('tagIDs', None)]:
            values = obj.get(field, [])
            if not isinstance(values, list):
                raise ValueError('标签或地点必须为数组')
            for key in values:
                if not isinstance(key, str) or key not in terms or (terms[key].dimension == 'location') != (dimension == 'location'):
                    raise ValueError(f'无效地点或标签: {key}')


def term_values(ids, terms, ancestors=False, source='explicit'):
    result = []
    visited = set()
    for key in ids:
        current, origin = terms.get(key), source
        redirected = set()
        while current and current.merged_into_id and current.id not in redirected:
            redirected.add(current.id)
            current = terms.get(current.merged_into_id)
        while current and current.id not in visited:
            visited.add(current.id)
            result.append({'id': current.id, 'name': current.name, 'dimension': current.dimension,
                           'aliases': current.aliases, 'source': origin})
            current = terms.get(current.parent_id) if ancestors else None
            origin = 'ancestor'
    return result


def documents(template, snapshot, terms=None):
    manifest = snapshot['manifest']
    validate(manifest)
    terms = taxonomy() if terms is None else terms
    validate_taxonomy(manifest, terms)
    pages = {p['data']['id']: p['data'] for p in snapshot['pages']}
    files = {f['path']: f for f in manifest.get('files', [])}

    def image(page_id):
        preview = pages[page_id].get('preview', {})
        return {k: {'key': snapshot['keys'].get(path, ''), 'sha256': files.get(path, {}).get('sha256', ''),
                    'asset_id': files.get(path, {}).get('sha256', path)} for k, path in preview.items()}

    shared = {'template_id': str(template.id), 'template_book_id': manifest.get('templateBookID', str(template.id)),
              'version': manifest.get('packageVersion', 1), 'book_title': template.title, 'series': template.series.slug,
              'book_page_count': len(pages), 'book_position': template.position, 'content_kind': template.content_kind}
    cover = manifest['coverPageID']
    result = [('book', str(template.id), 0, dict(shared, title=template.title, page_count=len(pages),
               page_ids=list(pages), images=[image(cover)], fields=[{'text': template.title, 'field': 'title', 'source': 'explicit', 'rank': 0}], terms=[]))]
    for unit in manifest.get('readingUnits', []):
        if not unit.get('searchEnabled') or exclusion_reason(manifest, unit):
            continue
        ids = page_ids(unit)
        if any(not pages[p].get('preview', {}).get('thumbnailPath') or not pages[p].get('preview', {}).get('largePath') for p in ids):
            raise ValueError('可搜索跨页缺少左右预览')
        mode = unit.get('locationMode', 'none')
        places = unit.get('locationIDs', []) if mode == 'explicit' else manifest.get('metadata', {}).get('defaultLocationIDs', []) if mode == 'inherit' else []
        if mode == 'inherit' and manifest.get('metadata', {}).get('locationScope') != 'single_city':
            raise ValueError('多城市模板不能继承全部地点，请逐跨页指定')
        effective = term_values(places, terms, True, 'context' if mode == 'inherit' else 'explicit')
        effective += term_values(unit.get('tagIDs', []), terms)
        fields = [{'text': unit['title'], 'field': 'title', 'source': 'explicit', 'rank': 0}]
        for p in ids:
            meta = manifest.get('pageMetadata', {}).get(p, {})
            fields.append({'text': meta.get('displayTitle') or clean_title(pages[p]['title']), 'field': 'page_title', 'source': 'page', 'rank': 4})
            effective += term_values(meta.get('locationIDs', []), terms, True, 'page')
            effective += term_values(meta.get('tagIDs', []), terms, False, 'page')
        fields += [{'text': word, 'field': 'keyword', 'source': 'explicit', 'rank': 5} for word in unit.get('searchKeywords', [])]
        doc = dict(shared, unit_id=unit['id'], position=unit['position'], title=unit['title'], page_count=2, page_ids=ids, images=[image(p) for p in ids], fields=fields, terms=effective)
        result.append(('spread', unit['id'], unit['position'], doc))
    book = result[0][3]
    book['terms'] = term_values(manifest.get('metadata', {}).get('defaultLocationIDs', []), terms, True, 'context')
    for _, _, _, doc in result[1:]:
        book['terms'] += doc.get('terms', [])
        book['fields'] += [dict(f, field='child_text', rank=7, source='child') for f in doc.get('fields', [])]
    return result


def index_version(template, version):
    docs = documents(template, version.snapshot)
    CatalogEntry.objects.filter(version=version).delete()
    entries = []
    for kind, key, pos, doc in docs:
        texts = [f['text'] for f in doc.get('fields', [])]
        texts += [v for t in doc.get('terms', []) for v in [t['name'], *t['aliases']]]
        grouped = {name:'\n'.join(normalize(f['text']) for f in doc.get('fields', []) if f['field']==name) for name in ('title','page_title','keyword','child_text')}
        entries.append(CatalogEntry(version=version, entity_type=kind, entity_id=key, position=pos, document=doc, search_text='\n'.join(normalize(v) for v in texts),
                                   title_text=grouped['title'], page_text=grouped['page_title'], keyword_text=grouped['keyword'], child_text=grouped['child_text']))
    CatalogEntry.objects.bulk_create(entries)
    # Read identities back for MySQL variants that do not return bulk-insert PKs.
    persisted = list(CatalogEntry.objects.filter(version=version).only('id', 'entity_type', 'entity_id'))
    by_id = {(e.entity_type, e.entity_id): e.pk for e in persisted}
    links = []
    for kind, key, _, doc in docs:
        unique = {}
        for term in doc.get('terms', []):
            rank = 6 if term['source'] in ('ancestor','context') else 1 if term['dimension']=='location' else 5
            previous = unique.get(term['id'])
            if previous is None or rank<previous[1]:unique[term['id']]=(term['dimension'],rank)
        links.extend(CatalogEntryTerm(entry_id=by_id[(kind,key)], taxon_id=tid, dimension=dim,rank=rank) for tid,(dim,rank) in unique.items())
    CatalogEntryTerm.objects.bulk_create(links)
    return len(docs) - 1


def query_terms(query, terms):
    # Longest controlled term first; unknown remainder is retained as a condition.
    aliases = sorted({normalize(v) for t in terms.values() for v in [t.name, *t.aliases] if v}, key=lambda v: (-len(v), v))
    result = []
    for chunk in normalize(query).split():
        while chunk:
            match = next((a for a in aliases if chunk.startswith(a)), None)
            if match:
                result.append(match); chunk = chunk[len(match):]
            else:
                split = next((i for i in range(1, len(chunk)) if any(chunk[i:].startswith(a) for a in aliases)), len(chunk))
                result.append(chunk[:split]); chunk = chunk[split:]
    return result


def match_document(doc, words, filters, terms):
    effective = doc.get('terms', [])
    for dimension, ids in filters.items():
        if ids and not any(t['id'] in ids and t['dimension'] == dimension for t in effective):
            return None
    reasons, ranks = [], []
    for word in words:
        options = []
        for f in doc.get('fields', []):
            value = normalize(f['text'])
            if word in value:
                rank = f['rank']
                if f['field'] == 'title':
                    rank = 0 if value == word else 2 if value.startswith(word) else 3
                options.append((rank, f['field'], f['source']))
        targets = {t.id for t in terms.values() if word in [normalize(t.name), *[normalize(a) for a in t.aliases]]}
        for t in effective:
            if t['id'] in targets:
                rank = 6 if t['source'] in ('ancestor', 'context') else 1 if t['dimension'] == 'location' else 5
                options.append((rank, t['dimension'], t['source']))
        if not options:
            return None
        rank, field, source = min(options)
        ranks.append(rank); reasons.append({'term': word, 'field': field, 'source': source})
    return (max(ranks, default=9), sum(ranks), reasons)


def representation(doc, kind, entity_id, reasons):
    result = {k: deepcopy(v) for k, v in doc.items() if k not in ('fields', 'terms', 'images')}
    result.update(id=f"{doc['template_id']}:{doc['version']}:{entity_id}", entity_type=kind,
                  matched_fields=reasons, capabilities={'can_preview': True, 'can_add': True})
    result['previews'] = [{variant: dict(asset_id=a['asset_id'], sha256=a['sha256'], url=storage.sign(a['key']) if a['key'] else '', expires_at=int(time.time()) + 300)
                           for variant, a in img.items()} for img in doc['images']]
    result['tags'] = [t['name'] for t in doc.get('terms', []) if t['dimension'] != 'location']
    result['search_fields'] = doc.get('fields', [])
    result['search_terms'] = doc.get('terms', [])
    return result


def run_search(params, owner, draft=None):
    kind, query = params.get('kind'), params.get('q', '')
    if kind not in ('book', 'spread') or not isinstance(query, str) or len(query) > 100:
        raise ValidationError('kind 需为 book/spread，关键词最多 100 字符')
    try:
        limit = int(params.get('limit', 24))
    except (ValueError, TypeError):
        raise ValidationError('limit 无效')
    if not 1 <= limit <= 60 or params.get('sort', 'relevance') not in ('relevance', 'recent'):
        raise ValidationError('limit 或排序无效')
    content_kind = params.get('content_kind', 'journal')
    if content_kind not in ('journal', 'album', 'all'):
        raise ValidationError('content_kind 需为 journal/album/all')
    terms = taxonomy()
    filters = {}
    for dim, field in [('location', 'location_ids'), ('theme', 'theme_ids'), ('style', 'style_ids'), ('usage', 'usage_ids')]:
        if not isinstance(params.get(field, ''), str):
            raise ValidationError(f'{field} 必须为逗号分隔的 ID 字符串')
        ids = set(filter(None, params.get(field, '').split(',')))
        if any(key not in terms or terms[key].dimension != dim for key in ids):
            raise ValidationError(f'{field} 含未知词项')
        ids = {terms[key].merged_into_id or key for key in ids}
        filters[dim] = ids
    state = SearchState.objects.filter(id=1).values_list('revision', flat=True).first() or 1
    visibility = list(Template.objects.filter(audience='public').order_by('id').values_list('id', 'current_id', 'active', 'revision', 'series_id', 'content_kind'))
    series_state = list(Series.objects.order_by('id').values_list('id', 'active', 'position'))
    revision = hashlib.sha256(str((state, visibility, series_state)).encode()).hexdigest()[:20]
    signature = hashlib.sha256(json.dumps([content_kind, kind, normalize(query), {k: sorted(v) for k, v in filters.items()}, params.get('series', ''), params.get('sort', 'relevance'), str(owner), limit], sort_keys=True).encode()).hexdigest()
    offset = 0
    if params.get('cursor'):
        try:
            cursor = signing.loads(params['cursor'], salt='preset-search', max_age=3600)
            if cursor['revision'] != revision or cursor['signature'] != signature:
                raise StaleCursor()
            offset = cursor['offset']
        except signing.BadSignature:
            raise StaleCursor()
    words = query_terms(query, terms)
    if draft:
        template, snapshot = draft
        candidates = [(k, key, pos, doc, template.position, 0) for k, key, pos, doc in documents(template, snapshot, terms) if k == kind]
    else:
        entries = CatalogEntry.objects.filter(entity_type=kind, version__template__audience='public', version__template__active=True, version__template__deleted_at__isnull=True,
            version__template__series__active=True, version_id=F('version__template__current_id'))
        if content_kind != 'all':
            entries = entries.filter(version__template__content_kind=content_kind)
        if params.get('series'):
            entries = entries.filter(version__template__series__slug=params['series'])
        for word in words:
            entries = entries.filter(search_text__contains=word)
        for dim, ids in filters.items():
            if ids:
                entries = entries.filter(pk__in=CatalogEntryTerm.objects.filter(dimension=dim, taxon_id__in=ids).values('entry_id'))
        ranks = []
        for index, word in enumerate(words):
            target_ids = {t.id for t in terms.values() if word in [normalize(t.name), *[normalize(a) for a in t.aliases]]}
            clauses = []
            for rank in (0,1,2,3,4,5,6,7):
                condition = Q(pk__in=CatalogEntryTerm.objects.filter(taxon_id__in=target_ids,rank=rank).values('entry_id')) if target_ids else Q(pk__in=[])
                if rank==0:condition |= Q(title_text=word)
                elif rank==2:condition |= Q(title_text__startswith=word)
                elif rank==3:condition |= Q(title_text__contains=word)
                elif rank==4:condition |= Q(page_text__contains=word)
                elif rank==5:condition |= Q(keyword_text__contains=word)
                elif rank==7:condition |= Q(child_text__contains=word)
                clauses.append(When(condition,then=Value(rank)))
            field = f'word_rank_{index}'
            entries = entries.annotate(**{field:Case(*clauses,default=Value(9),output_field=IntegerField())}).filter(**{field+'__lt':9})
            ranks.append(F(field))
        worst = Greatest(*ranks) if len(ranks)>1 else ranks[0] if ranks else Value(9)
        total_rank = sum(ranks,Value(0))
        entries = entries.annotate(worst_rank=worst,total_rank=total_rank)
        order = ['worst_rank','total_rank','version__template__position','version__template_id','position','entity_id']
        if params.get('sort')=='recent':order=['-version_id','version__template__position','version__template_id','position','entity_id']
        count = entries.count()
        selected = entries.order_by(*order).values('document','entity_type','entity_id')[offset:offset+limit]
        output = []
        for entry in selected:
            hit = match_document(entry['document'],words,filters,terms)
            if hit is not None:output.append(representation(entry['document'],entry['entity_type'],entry['entity_id'],hit[2]))
        more = offset + limit < count
        next_cursor = signing.dumps({'revision':revision,'signature':signature,'offset':offset+limit},salt='preset-search') if more else None
        return dict(kind=kind,query=query,catalog_revision=revision,search_revision=state,taxonomy_revision=state,
                    entries=output,total=count,next_cursor=next_cursor,has_more=more)
    matches = []
    for k, key, pos, doc, book_pos, vid in candidates:
        hit = match_document(doc, words, filters, terms)
        if hit is not None:
            score = (hit[0], hit[1], book_pos, doc['template_id'], pos, key)
            if params.get('sort') == 'recent': score = (-vid, book_pos, doc['template_id'], pos, key)
            matches.append((score, k, key, doc, hit[2]))
    matches.sort(key=lambda row: row[0])
    page = matches[offset:offset + limit]
    more = offset + limit < len(matches)
    next_cursor = signing.dumps({'revision': revision, 'signature': signature, 'offset': offset + limit}, salt='preset-search') if more else None
    return dict(kind=kind, query=query, catalog_revision=revision, search_revision=state, taxonomy_revision=state,
                entries=[representation(doc, k, key, reasons) for _, k, key, doc, reasons in page], total=len(matches), next_cursor=next_cursor, has_more=more)
