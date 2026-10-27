import json
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from common.exceptions import APIError
from .dataset import canonical, sha, validate, difference
from .models import RegionDataset, RegionState, RegionPublication


class RegionError(APIError):
    def __init__(self, code, message):
        super().__init__(message, code=-1, status_code=409,
                         details={'region_error': code, 'recovery': 'refresh_regions_and_reselect'})


def stage(nodes, fetched_at=None):
    counts = validate(nodes)
    digest = sha(canonical(nodes))
    current = RegionState.objects.filter(pk=1).select_related('current').first()
    old = json.loads(current.current.artifact)['regions'] if current and current.current else []
    if current and current.current and current.current.content_sha256 == digest: return current.current, False
    previous = RegionDataset.objects.filter(content_sha256=digest).exclude(status='revoked').first()
    if previous: return previous, True
    version = 'cn-' + timezone.localtime().strftime('%Y%m%d') + '-' + uuid.uuid4().hex[:12]
    artifact = canonical(dict(schema_version=1, dataset_version=version, regions=nodes))
    return RegionDataset.objects.create(version=version, fetched_at=fetched_at or timezone.now(), counts=counts,
        content_sha256=digest, artifact_sha256=sha(artifact), artifact=artifact, diff=difference(old, nodes)), True


@transaction.atomic
def publish(version, actor, reason):
    if not actor or not reason: raise ValueError('audit_reason_required')
    RegionState.objects.get_or_create(pk=1)
    state = RegionState.objects.select_for_update().get(pk=1)
    data = RegionDataset.objects.select_for_update().get(pk=version)
    if data.status == 'revoked': raise ValueError('dataset_revoked')
    if sha(data.artifact) != data.artifact_sha256: raise ValueError('artifact_corrupt')
    validate(json.loads(data.artifact)['regions'])
    if state.current_id == version: return state
    data.status = 'published'
    if not data.published_at: data.published_at = timezone.now()
    data.save(update_fields=['status','published_at'])
    state.current = data; state.release_sequence += 1; state.save()
    RegionPublication.objects.create(sequence=state.release_sequence, dataset=data, actor=actor[:120], reason=reason[:500])
    return state


def current_dataset():
    state = RegionState.objects.select_related('current').filter(pk=1).first()
    if not state or not state.current or state.current.status != 'published':
        raise RegionError('REGION_DATA_UNAVAILABLE', '地区数据暂不可用，请稍后重试')
    return state.current


def normalize_address(address, product=None):
    """Call AFTER idempotency lookup; never rewrite a retried order payload."""
    if not address.get('region_version') and not any(address.get(k) for k in ('province_code','city_code','district_code')):
        return address  # Legacy clients and immutable queued jobs remain supported.
    current = current_dataset()
    old = RegionDataset.objects.filter(pk=address.get('region_version'), status='published').first()
    if old is None: raise RegionError('REGION_DATA_UPDATE_REQUIRED', '请更新地区数据并重新选择所在地区')
    nodes = {n['code']: n for n in json.loads(current.artifact)['regions']}
    previous = {n['code']: n for n in json.loads(old.artifact)['regions']}
    parent = None; names = []; result = dict(address)
    for level in ('province','city','district'):
        code = address.get(level+'_code')
        result[level+'_name'] = None
        if not code:
            if level == 'province': raise RegionError('REGION_INVALID_PATH','请选择省份')
            continue
        node = nodes.get(code); was = previous.get(code)
        if not node or not was or node['parent_code'] != was['parent_code'] or node['level'] != was['level']:
            raise RegionError('REGION_RESELECT_REQUIRED','所选地区已调整，请重新选择')
        if node['level'] != level or node['parent_code'] != parent:
            raise RegionError('REGION_INVALID_PATH','省市区归属不匹配，请重新选择')
        result[level+'_name'] = node['name']; names.append(node['name']); parent = code
    if not parent or not nodes[parent]['selectable_leaf']:
        raise RegionError('REGION_INVALID_PATH','请选择完整的所在地区')
    if product:
        # Supported legacy shipping labels are resolved on the server, never
        # accepted solely from the client for a structured address.
        allowed = product.regions
        if '中国大陆' in allowed: shipping = '中国大陆'
        else:
            aliases = set(names)
            for name in names:
                if name.endswith(('省','市')): aliases.add(name[:-1])
            shipping = next((r for r in allowed if r in aliases), None)
        if shipping is None: raise RegionError('ADDRESS_NOT_DELIVERABLE','此地区暂不支持配送，请选择其他地址')
        result['region'] = shipping
    result['region_version'] = current.version
    result['formatted_address'] = ' '.join(names + [address['detail']])
    return result
