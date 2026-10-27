"""Bounded, server-only synchronization. Exceptions never contain request URLs."""
import json
import uuid
import requests
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import RegionState, RegionSyncRun
from .dataset import normalize
from .services import stage


class SyncError(Exception): pass


@transaction.atomic
def acquire(force=False):
    RegionState.objects.get_or_create(pk=1)
    state = RegionState.objects.select_for_update().get(pk=1)
    now = timezone.now()
    if state.lock_until and state.lock_until > now: return None
    if not force and state.next_check_at and state.next_check_at > now: return None
    token = str(uuid.uuid4()); state.lock_token = token; state.lock_until = now + timedelta(minutes=5); state.save()
    return token


@transaction.atomic
def reserve(token):
    state = RegionState.objects.select_for_update().get(pk=1)
    now = timezone.now()
    if state.lock_token != token or not state.lock_until or state.lock_until <= now: raise SyncError('lock_lost')
    if state.budget_date != now.date(): state.budget_date = now.date(); state.budget_used = 0
    budget = settings.REGIONS_DAILY_REQUEST_BUDGET
    if budget <= 0 or state.budget_used >= budget: raise SyncError('daily_budget_exhausted')
    state.budget_used += 1; state.lock_until = now + timedelta(minutes=5); state.save()


def synchronize(force=False):
    token = acquire(force)
    if not token: return None
    run = RegionSyncRun.objects.create()
    error = None
    try:
        if not settings.AMAP_WEB_SERVICE_KEY: raise SyncError('key_not_configured')
        reserve(token); run.request_count = 1; run.save(update_fields=['request_count'])
        try:
            with requests.get('https://restapi.amap.com/v3/config/district', params={
                'key': settings.AMAP_WEB_SERVICE_KEY, 'keywords':'中国', 'subdistrict':3,
                'extensions':'base', 'page':1, 'offset':20}, timeout=(5,30), stream=True) as response:
                if response.status_code != 200: raise SyncError('upstream_http_'+str(response.status_code))
                payload = bytearray()
                for chunk in response.iter_content(65536):
                    payload.extend(chunk)
                    if len(payload)>10*1024*1024: raise SyncError('upstream_too_large')
            raw = json.loads(payload)
        except (requests.RequestException, ValueError): raise SyncError('upstream_transport_or_json') from None
        if raw.get('status') != '1':
            code = str(raw.get('infocode','unknown'))
            raise SyncError('upstream_'+(code if code.isdigit() else 'rejected'))
        # A country root is one result, so the root result fits a page. Verify
        # completeness rather than silently publishing truncated descendants.
        if str(raw.get('count')) != '1': raise SyncError('unexpected_root_pagination')
        nodes = normalize(raw)
        with transaction.atomic():
            state = RegionState.objects.select_for_update().get(pk=1)
            if state.lock_token != token or state.lock_until <= timezone.now(): raise SyncError('lock_lost')
            data, changed = stage(nodes)
            run.dataset_version = data.version; run.status = 'candidate' if changed else 'unchanged'
            state.failures = 0; state.last_checked_at = timezone.now()
            state.next_check_at = timezone.now()+timedelta(days=settings.REGIONS_SYNC_DAYS)
            state.save()
    except Exception as exc:
        error = str(exc) if isinstance(exc, (SyncError, ValueError)) else type(exc).__name__
        # Codes only; never persist a third-party exception containing the key.
        run.error_code = error[:100] if error.replace('_','').isalnum() else 'sync_validation_failed'
        run.status = 'failed'
    finally:
        with transaction.atomic():
            state = RegionState.objects.select_for_update().get(pk=1)
            if state.lock_token == token:
                if error:
                    state.failures += 1
                    hours = [1,6,24][min(state.failures-1,2)]
                    if run.error_code in ['upstream_10001','upstream_10002','upstream_10003','upstream_10004']:
                        hours = 24 * settings.REGIONS_SYNC_DAYS
                    state.next_check_at = timezone.now()+timedelta(hours=hours)
                state.lock_token=''; state.lock_until=None; state.save()
        run.finished_at=timezone.now(); run.save()
    return run
