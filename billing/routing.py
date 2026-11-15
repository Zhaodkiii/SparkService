"""Deployment routing is independent of Apple's purchase environment."""
import uuid
from datetime import timedelta
import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import BillingIdentity, CurrencyEvent, WebhookDelivery

DEV_PREFIX = 'd1a7de00'

def new_identity_id():
    value = str(uuid.uuid4())
    return uuid.UUID(DEV_PREFIX + value[8:]) if settings.BILLING_DEPLOYMENT == 'development' else uuid.UUID(value)

def development_id(value):
    try:
        value = str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return False
    return value.startswith(DEV_PREFIX)

def event_ids(data):
    if data.get('type') == 'TRANSFER':
        return [x for key in ('transferred_from', 'transferred_to') for x in (data.get(key) if isinstance(data.get(key), list) else []) if isinstance(x, str)]
    return [data.get('app_user_id')]

@transaction.atomic
def ingest(data, *, relay=False):
    ids = event_ids(data)
    local_ids = []
    for value in ids:
        try: local_ids.append(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError): pass
    known = BillingIdentity.objects.filter(rc_project_id=settings.REVENUECAT_PROJECT_ID, rc_app_user_id__in=local_ids).exists()
    dev = any(development_id(value) for value in ids)
    if relay and not known:
        return False  # Sender retains the event until identity data is available.
    event, _ = CurrencyEvent.objects.get_or_create(
        event_id=settings.REVENUECAT_PROJECT_ID + ':' + data['id'], defaults={'payload': data})
    if not relay and settings.BILLING_DEPLOYMENT == 'production' and dev:
        WebhookDelivery.objects.get_or_create(event=event)
        if not known:
            if event.state == 'pending' and event.identity_id is None:
                event.state = 'forwarding'
                event.save(update_fields=['state'])
            return True
    from .tasks import process_event
    process_event(event.pk)
    return True

def deliver_pending():
    if settings.BILLING_DEPLOYMENT != 'production': return
    url, token = settings.BILLING_DEV_RELAY_URL, settings.BILLING_RELAY_TOKEN
    if not url or not token: return
    ids = list(WebhookDelivery.objects.filter(delivered_at__isnull=True, next_attempt_at__lte=timezone.now()).values_list('pk', flat=True)[:5])
    for pk in ids:
        # Lease commits before network I/O. A crashed worker is retried after two minutes.
        with transaction.atomic():
            row = WebhookDelivery.objects.select_for_update().select_related('event').get(pk=pk)
            if row.delivered_at or row.next_attempt_at > timezone.now(): continue
            row.attempts += 1
            row.next_attempt_at = timezone.now() + timedelta(minutes=2)
            row.save(update_fields=['attempts', 'next_attempt_at'])
            payload = row.event.payload
        status = 0
        accepted = False
        try:
            response = httpx.post(url, json={'event': payload}, headers={'Authorization': token}, timeout=10, follow_redirects=False)
            status = response.status_code
            accepted = status == 200 and response.json().get('received') is True
        except (httpx.HTTPError, ValueError, AttributeError): pass
        with transaction.atomic():
            row = WebhookDelivery.objects.select_for_update().get(pk=pk)
            row.last_status = status
            if accepted:
                row.delivered_at = timezone.now()
                CurrencyEvent.objects.filter(pk=row.event_id, state='forwarding').update(state='forwarded')
            else:
                row.next_attempt_at = timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 7)))
            row.save()
