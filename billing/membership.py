"""Verified entitlement is authority; subscription details only describe renewal state."""
from datetime import datetime, timedelta, timezone as dt_timezone
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from .models import MembershipSnapshot, ContentOffer
from .provider import RevenueCat
from .flags import enabled


def timestamp(value):
    if type(value) is not int: return None
    try: return datetime.fromtimestamp(value / 1000, dt_timezone.utc)
    except (ValueError, OverflowError, OSError): return None


def refresh(identity, force=False):
    if connection.in_atomic_block: return False
    started = timezone.now()
    cached = MembershipSnapshot.objects.filter(identity=identity).first()
    if not force and cached and not cached.needs_sync and cached.verified_at and cached.verified_at > started-timedelta(minutes=5):
        return True
    provider = RevenueCat()
    result = provider.customer(identity)
    if result.status != 200: return False
    active = result.body.get('active_entitlements')
    if not isinstance(active, dict) or not isinstance(active.get('items'), list): return False
    until = None
    for item in active['items']:
        if item.get('entitlement_id') == settings.REVENUECAT_MEMBER_ENTITLEMENT_ID:
            until = timestamp(item.get('expires_at'))
            if until is None: return False
    if until is None and active.get('next_page'): return False
    details = provider.subscriptions(identity)
    detail = None
    details_complete = details.status == 200 and isinstance(details.body.get('items'), list) and not details.body.get('next_page')
    if details_complete:
        candidates = [s for s in details.body['items'] if s.get('environment') == identity.wallet_domain and
                      any(e.get('id') == settings.REVENUECAT_MEMBER_ENTITLEMENT_ID for e in s.get('entitlements', {}).get('items', []))]
        if candidates:
            detail = max(candidates, key=lambda s: (s.get('gives_access') is True, s.get('current_period_ends_at') or 0))
    with transaction.atomic():
        row, _ = MembershipSnapshot.objects.select_for_update().get_or_create(identity=identity)
        # Ignore HTTP results started before a newer refresh or webhook invalidation.
        if (row.verified_at and row.verified_at > started) or (row.last_event_at and row.last_event_at > started): return False
        row.access_granted = bool(detail and detail.get('gives_access') is True)
        row.active_until = until
        row.verified_at = started
        row.needs_sync = False
        if detail:
            row.subscription_status = detail.get('status') or 'unknown'
            row.auto_renewal_status = detail.get('auto_renewal_status') or 'unknown'
            row.product_id = detail.get('product_id') or ''
            for entitlement in detail.get('entitlements', {}).get('items', []):
                for product in entitlement.get('products', {}).get('items', []):
                    if product.get('id') == row.product_id:
                        row.product_id = product.get('store_identifier') or row.product_id
            row.period_ends_at = timestamp(detail.get('current_period_ends_at'))
        else:
            row.subscription_status = 'active' if until and until > started else 'inactive'
            row.auto_renewal_status = 'unknown'
            row.product_id = ''
            row.period_ends_at = None
        row.save()
    return True


def status(identity, force=False):
    synced = refresh(identity, force=force)
    row = MembershipSnapshot.objects.filter(identity=identity).first()
    now = timezone.now()
    fresh = bool(row and row.verified_at and row.verified_at >= now-timedelta(hours=1))
    active = is_active(row, identity, now)
    return dict(active=active, expires_at=row.active_until if row else None,
                verified_at=row.verified_at if row else None, sync_state='fresh' if synced else 'stale',
                status=row.subscription_status if row else 'unknown',
                auto_renewal_status=row.auto_renewal_status if row else 'unknown',
                period_ends_at=row.period_ends_at if row else None,
                product_id=row.product_id if row else '', wallet_domain=identity.wallet_domain,
                sales_enabled=enabled('MEMBERSHIP_SALES_ENABLED', identity),
                member_content_count=ContentOffer.objects.filter(state='active', current_policy_revision__access_mode__in=['pro_only','pro_or_diamond']).count())


def is_active(row, identity, now=None):
    now = now or timezone.now()
    if not row or identity.state != 'active' or not row.verified_at or row.verified_at < now-timedelta(hours=1): return False
    if row.active_until and row.active_until > now: return True
    # A verified grace period can extend access beyond the paid period; short cache only.
    return bool(row.access_granted and row.subscription_status == 'in_grace_period' and row.verified_at > now-timedelta(minutes=5))
