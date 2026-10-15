"""Immutable snapshots. This module does not perform network or filesystem I/O."""
from copy import deepcopy


def select(snapshot, page_ids):
    manifest = deepcopy(snapshot['manifest'])
    indexed = {p['data']['id']: p for p in snapshot['pages']}
    if not page_ids or len(set(page_ids)) != len(page_ids) or not set(page_ids) <= indexed.keys():
        raise ValueError('Invalid selected pages')
    pages = [deepcopy(indexed[i]) for i in page_ids]
    paths = set().union(*(set(p['files']) for p in pages))
    manifest['pages'] = [p for i in page_ids for p in manifest['pages'] if p['id'] == i]
    manifest['objectTable'] = {k: v for k, v in manifest['objectTable'].items() if v in paths}
    manifest['assetTable'] = {k: v for k, v in manifest['assetTable'].items() if v['path'] in paths}
    manifest['files'] = [f for f in manifest['files'] if f['path'] in paths]
    if manifest['coverPageID'] not in page_ids:
        manifest['coverPageID'] = page_ids[0]
    if manifest.get('shellPageID') not in page_ids:
        manifest.pop('shellPageID', None)
    return dict(manifest=manifest, pages=pages, keys={p: snapshot['keys'][p] for p in paths})


def merge(base, added, after=''):
    if not base:
        return deepcopy(added)
    if base['manifest']['pageSize'] != added['manifest']['pageSize']:
        raise ValueError('页面尺寸与手帐不一致')
    result = deepcopy(base)
    left, right = result['manifest'], added['manifest']
    for field in ['objectTable', 'assetTable']:
        if left[field].keys() & right[field].keys():
            raise ValueError('Conflicting IDs; upload a newly namespaced page')
        left[field].update(right[field])
    existing = [p['id'] for p in left['pages']]
    if set(existing) & {p['id'] for p in right['pages']}:
        raise ValueError('Duplicate page ID')
    if after and after not in existing:
        raise ValueError('插入位置已不存在')
    index = existing.index(after) + 1 if after else len(existing)
    left['pages'][index:index] = deepcopy(right['pages'])
    result['pages'][index:index] = deepcopy(added['pages'])
    if set(result['keys']) & set(added['keys']):
        raise ValueError('Conflicting file paths')
    result['keys'].update(added['keys'])
    left['files'] += deepcopy(right['files'])
    left['requiredCapabilities'] = sorted(set(left['requiredCapabilities'] + right['requiredCapabilities']))
    left['requiredFonts'] = list({str(f): f for f in left.get('requiredFonts', []) + right.get('requiredFonts', [])}.values())
    return result
