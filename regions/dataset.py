"""Pure normalization/validation: no credentials and no network calls."""
import hashlib
import json
import re
from collections import Counter

LEVELS = {'province': 0, 'city': 1, 'district': 2}
MAINLAND = {f'{i:02d}0000' for i in [11,12,13,14,15,21,22,23,31,32,33,34,35,36,37,41,42,43,44,45,46,50,51,52,53,54,61,62,63,64,65]}
MUNICIPALITIES = {'110000', '120000', '310000', '500000'}
# Reviewed cities whose immediate administrative descendants are townships.
NO_DISTRICTS = {'441900', '442000', '460400', '620200'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def validate(nodes, complete=True):
    if not isinstance(nodes, list) or not nodes: raise ValueError('empty_dataset')
    by_code = {}
    for n in nodes:
        if not isinstance(n, dict) or not re.fullmatch(r'\d{6}', n.get('code', '')): raise ValueError('invalid_code')
        if n['code'] in by_code: raise ValueError('duplicate_code')
        if n.get('level') not in LEVELS or not isinstance(n.get('name'), str) or not n['name'].strip(): raise ValueError('invalid_node')
        if not isinstance(n.get('selectable_leaf'), bool): raise ValueError('invalid_leaf')
        by_code[n['code']] = n
    children = Counter(n.get('parent_code') for n in nodes)
    for n in nodes:
        parent = by_code.get(n.get('parent_code'))
        if n['level'] == 'province':
            if n.get('parent_code') is not None or n['selectable_leaf']: raise ValueError('invalid_province')
        elif parent is None or LEVELS[parent['level']] >= LEVELS[n['level']]: raise ValueError('invalid_parent')
        if n['selectable_leaf'] != (children[n['code']] == 0): raise ValueError('inconsistent_leaf')
        if n['level'] == 'city' and n['selectable_leaf'] and n['code'] not in NO_DISTRICTS: raise ValueError('unreviewed_city_leaf')
    counts = dict(Counter(n['level'] for n in nodes))
    if complete:
        if {n['code'] for n in nodes if n['level'] == 'province'} != MAINLAND: raise ValueError('incomplete_provinces')
        if counts.get('district', 0) < 2500 or counts.get('city', 0) < 280: raise ValueError('incomplete_dataset')
    return counts


def normalize(response):
    if response.get('status') != '1': raise ValueError('upstream_rejected')
    roots = response.get('districts')
    if not isinstance(roots, list) or len(roots) != 1 or roots[0].get('level') != 'country': raise ValueError('invalid_root')
    nodes = []
    def visit(raw, parent=None):
        code, level = str(raw.get('adcode', '')), raw.get('level')
        if level == 'street': return
        if level not in LEVELS: raise ValueError('unknown_level')
        kids = raw.get('districts', [])
        if not isinstance(kids, list): raise ValueError('invalid_children')
        # AMap synthetic city groups under municipalities are presentation nodes.
        if parent in MUNICIPALITIES and level == 'city':
            if not kids: raise ValueError('empty_municipality')
            for child in kids: visit(child, parent)
            return
        # Province-administered counties may be reported as city, but their
        # six-digit code has a non-zero county suffix. Normalize the real level.
        if level == 'city' and code[-2:] != '00': level = 'district'
        real_kids = [k for k in kids if k.get('level') != 'street']
        if level == 'district' and real_kids: raise ValueError('district_with_administrative_child')
        nodes.append(dict(code=code, name=raw.get('name'), level=level, parent_code=parent,
                          selectable_leaf=not real_kids, sort_order=int(code)))
        for child in real_kids: visit(child, code)
    for province in roots[0].get('districts', []):
        if province.get('adcode') in MAINLAND: visit(province)
    nodes.sort(key=lambda n: n['code'])
    validate(nodes)
    return nodes


def difference(old, new):
    before, after = {n['code']: n for n in old}, {n['code']: n for n in new}
    return dict(added=sorted(after.keys()-before.keys()), removed=sorted(before.keys()-after.keys()),
                changed=[code for code in sorted(before.keys() & after.keys()) if before[code] != after[code]])
