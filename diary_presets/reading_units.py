"""Portable reading-unit validation. No Django, network or filesystem dependencies."""
from copy import deepcopy
import re
import unicodedata
import uuid

ROLES = {'front_cover', 'back_cover', 'shell', 'content', 'blank'}


def normalize(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def clean_title(value):
    value = re.sub(r'^\d+[_\s-]*', '', value)
    value = re.sub(r'[_-](?:分层|照片相框|照片卡|适量分层|文字与卡片|\d+层|\d+(?:\.\d+)?x\d+).*$', '', value)
    value = re.sub(r'[-_](?:分层)?[vV]\d+.*$', '', value)
    return value.strip(' ·_-')


def suggest(manifest):
    """Conservative title-based candidates. Nothing is automatically confirmed."""
    pages = manifest['pages']
    result = deepcopy(manifest)
    metadata = result.setdefault('pageMetadata', {})
    units = []
    index = 0
    while index < len(pages):
        page = pages[index]
        role = 'front_cover' if page['id'] == manifest['coverPageID'] else 'shell' if page['id'] == manifest.get('shellPageID') else 'content'
        metadata.setdefault(page['id'], {'contentRole': role, 'displayTitle': clean_title(page.get('title', page['id']))})
        pair = None
        if role == 'content' and index + 1 < len(pages):
            other = pages[index + 1]
            left = re.split('左页', clean_title(page.get('title', '')))[0].rstrip(' ·_-')
            right = re.split('右页', clean_title(other.get('title', '')))[0].rstrip(' ·_-')
            if '左页' in page.get('title', '') and '右页' in other.get('title', '') and left == right and other['id'] not in (manifest['coverPageID'], manifest.get('shellPageID')):
                pair = other
                metadata.setdefault(other['id'], {'contentRole': 'content', 'displayTitle': clean_title(other.get('title', other['id']))})
        ids = [page['id']] + ([pair['id']] if pair else [])
        unit = {'id': str(uuid.uuid5(uuid.NAMESPACE_URL, manifest['templateBookID'] + ':' + '|'.join(ids))),
                'kind': 'spread' if pair else 'cover' if role == 'front_cover' else 'single',
                'title': re.split('左页', clean_title(page.get('title', page['id'])))[0].rstrip(' ·_-'),
                'position': len(units), 'leftPageID': page['id'] if pair else None,
                'rightPageID': pair['id'] if pair else page['id'], 'pairingSource': 'suggested',
                'searchEnabled': False, 'locationMode': 'none', 'locationIDs': [], 'tagIDs': [], 'searchKeywords': []}
        units.append(unit)
        index += 2 if pair else 1
    result['readingUnits'] = units
    result.setdefault('metadata', {'defaultLocationIDs': [], 'locationScope': 'mixed'})
    result['schemaVersion'] = 2
    return result


def page_ids(unit):
    return [unit[k] for k in ('leftPageID', 'rightPageID') if unit.get(k)]


def validate(manifest):
    if manifest.get('schemaVersion', 1) == 1:
        if manifest.get('readingUnits'):
            raise ValueError('阅读单元需要 schemaVersion=2')
        return
    if manifest.get('schemaVersion') != 2:
        raise ValueError('不支持的资源协议版本')
    ids = [p['id'] for p in manifest['pages']]
    metadata = manifest.get('pageMetadata', {})
    if not isinstance(metadata, dict) or any(not isinstance(p, dict) for p in metadata.values()):
        raise ValueError('页面元数据必须为对象')
    if set(metadata) != set(ids) or any(p.get('contentRole') not in ROLES for p in metadata.values()):
        raise ValueError('每张页面必须有有效内容角色，且不得有外部页面')
    for meta in metadata.values():
        title = meta.get('displayTitle')
        if title is not None and (not isinstance(title, str) or not title.strip() or len(title) > 200):
            raise ValueError('页面展示标题需为 1–200 字符')
    units = manifest.get('readingUnits', [])
    if not isinstance(units, list) or len(units) > 100:
        raise ValueError('阅读单元数量无效')
    seen, expanded = set(), []
    for i, unit in enumerate(units):
        if not isinstance(unit, dict):
            raise ValueError('阅读单元必须为对象')
        if not isinstance(unit.get('id'), str) or not unit['id'] or len(unit['id']) > 200 or unit['id'] in seen:
            raise ValueError('跨页 ID 为空、重复或过长')
        seen.add(unit['id'])
        if not isinstance(unit.get('title'), str) or not unit['title'].strip() or len(unit['title']) > 200:
            raise ValueError('跨页标题需为 1–200 字符')
        if unit.get('kind') not in {'cover', 'single', 'spread'} or unit.get('pairingSource') not in {'explicit', 'suggested'}:
            raise ValueError('阅读单元类型或确认状态无效')
        members = page_ids(unit)
        if len(members) != len(set(members)) or not set(members) <= set(ids) or not members:
            raise ValueError('跨页引用缺失、重复或来自其他版本')
        if unit['kind'] != 'spread' and len(members) != 1:
            raise ValueError('单页/封面只能引用一张页面')
        if len(members) > 2 or type(unit.get('searchEnabled', False)) is not bool:
            raise ValueError('跨页搜索开关无效')
        if unit.get('locationMode', 'none') not in {'explicit', 'inherit', 'none'}:
            raise ValueError('地点继承模式无效')
        preview = unit.get('preview', {})
        if not isinstance(preview, dict) or any(k not in ('thumbnailPath', 'largePath') or not isinstance(v, str) or not v for k, v in preview.items()):
            raise ValueError('跨页预览引用无效')
        for field in ('locationIDs', 'tagIDs', 'searchKeywords'):
            values = unit.get(field, [])
            maximum, width = (10, 30) if field == 'searchKeywords' else (30, 120)
            if not isinstance(values, list) or len(values) > maximum or any(not isinstance(v, str) or not v.strip() or len(v) > width for v in values) or len(set(values)) != len(values):
                raise ValueError(f'{field} 包含无效或重复词项')
        if unit.get('searchEnabled') and exclusion_reason(manifest, unit):
            raise ValueError(exclusion_reason(manifest, unit))
        if type(unit.get('position')) is not int or unit['position'] != i:
            raise ValueError('阅读单元 position 必须与数组顺序一致')
        expanded.extend(members)
    if expanded != ids:
        raise ValueError('阅读单元展开顺序必须完整且与页面顺序一致')


def exclusion_reason(manifest, unit):
    if unit.get('kind') != 'spread' or len(page_ids(unit)) != 2:
        return '仅完整双页跨页可搜索'
    if unit.get('pairingSource') != 'explicit':
        return '配对尚未确认'
    if any(manifest.get('pageMetadata', {}).get(p, {}).get('contentRole') != 'content' for p in page_ids(unit)):
        return '封面、封底、外壳或空白页不可参与跨页搜索'
    return None


def subset(manifest, ids):
    """Preserve source roles even when a compatibility cover is reassigned."""
    if 'readingUnits' not in manifest:
        return
    old = manifest['readingUnits']
    units = []
    by_page = {p: u for u in old for p in page_ids(u)}
    used = set()
    for p in ids:
        if p in used:
            continue
        original = by_page.get(p)
        if not original:
            continue
        unit = deepcopy(original)
        members = page_ids(unit)
        start = ids.index(p)
        if all(m in ids for m in members) and ids[start:start + len(members)] == members:
            used.update(members)
        else:
            unit.update(id=str(uuid.uuid5(uuid.NAMESPACE_URL, unit['id'] + ':single:' + p)), kind='single', leftPageID=None, rightPageID=p, searchEnabled=False)
            unit.pop('preview', None)
            used.add(p)
        unit['position'] = len(units)
        units.append(unit)
    manifest['readingUnits'] = units
    manifest['pageMetadata'] = {p: manifest['pageMetadata'][p] for p in ids}


def retain_confirmed_metadata(previous, incoming):
    """Keep editorial work on reupload; changed previews require fresh confirmation."""
    if not previous or not previous.get('manifest', {}).get('readingUnits'):
        return incoming
    result = deepcopy(incoming)
    manifest = result['manifest']
    if manifest.get('schemaVersion') != 2:
        manifest = suggest(manifest)
        result['manifest'] = manifest

    def identity(value):
        # Upload namespaces are transport identities. Never match by display title.
        return re.sub(r'^(?:[0-9a-f]{24}|[0-9a-f-]{36})-', '', value)

    old_units = {tuple(identity(p) for p in page_ids(u)): u for u in previous['manifest']['readingUnits']}
    def previews(snapshot, ids):
        pages = {p['data']['id']: p['data'] for p in snapshot['pages']}
        return [snapshot['keys'].get(pages[p].get('preview', {}).get('largePath')) for p in ids]

    for unit in manifest['readingUnits']:
        old = old_units.get(tuple(identity(p) for p in page_ids(unit)))
        if not old or old.get('pairingSource') != 'explicit':
            continue
        unchanged = previews(previous, page_ids(old)) == previews(result, page_ids(unit))
        for field in ('id', 'title', 'locationMode', 'locationIDs', 'tagIDs', 'searchKeywords', 'annotation'):
            if field in old: unit[field] = deepcopy(old[field])
        unit['pairingSource'] = 'explicit' if unchanged else 'suggested'
        unit['searchEnabled'] = bool(old.get('searchEnabled')) and unchanged
        unit['requiresReview'] = not unchanged
    manifest['metadata'] = deepcopy(previous['manifest'].get('metadata', {}))
    old_pages = {identity(p): meta for p, meta in previous['manifest'].get('pageMetadata', {}).items()}
    for p in manifest.get('pageMetadata', {}):
        if identity(p) in old_pages: manifest['pageMetadata'][p] = deepcopy(old_pages[identity(p)])
    return result
