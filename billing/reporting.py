"""Idempotent reporting of authenticated, processed Apple events, without fulfillment."""
import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from django.db import transaction
from .models import StorePayment, RechargeProduct, ReconciliationCase

PURCHASES = {'INITIAL_PURCHASE', 'RENEWAL', 'NON_RENEWING_PURCHASE'}
LIFECYCLE = PURCHASES | {'CANCELLATION', 'UNCANCELLATION', 'EXPIRATION', 'BILLING_ISSUE', 'SUBSCRIPTION_EXTENDED', 'REFUND_REVERSED'}

def stamp(value):
    if type(value) is not int: return None
    try: return datetime.fromtimestamp(value / 1000, timezone.utc)
    except (ValueError, OverflowError, OSError): return None

@transaction.atomic
def project(event):
    data, identity = event.payload, event.identity
    kind = data.get('type')
    tx = data.get('transaction_id')
    if event.state != 'processed' or not identity or data.get('store') != 'APP_STORE': return
    if kind not in LIFECYCLE and not (kind=='VIRTUAL_CURRENCY_TRANSACTION' and data.get('source')=='in_app_purchase'): return
    environment=data.get('environment') or data.get('purchase_environment', '')
    if not isinstance(environment,str) or environment.lower()!=identity.wallet_domain: return
    if not isinstance(tx, str) or not tx or len(tx)>2048: return
    product = data.get('product_id')
    if not isinstance(product,str) or not product or len(product)>200: return
    digest = hashlib.sha256(f'{identity.rc_project_id}:{data.get("app_id")}:{identity.wallet_domain}:APP_STORE:{tx}'.encode()).hexdigest()
    is_topup = RechargeProduct.objects.filter(rc_project_id=identity.rc_project_id,apple_product_id=product).exists()
    row,_ = StorePayment.objects.get_or_create(transaction_digest=digest,defaults=dict(identity=identity,store_transaction_id=tx,product_id=product,kind='recharge' if is_topup else 'subscription' if kind!='NON_RENEWING_PURCHASE' else 'other'))
    row = StorePayment.objects.select_for_update().get(pk=row.pk)
    if row.identity_id != identity.pk or row.product_id != product:
        ReconciliationCase.objects.get_or_create(identity=identity,kind='payment_identity_conflict',evidence={'payment_id':str(row.pk)})
        return
    row.events.add(event)
    if kind in PURCHASES:
        row.payment_confirmed=True
        row.purchased_at=stamp(data.get('purchased_at_ms')) or row.purchased_at
        # Monetary fields belong only to purchase events, not cancellation/renewal preferences.
        currency=data.get('currency')
        try:
            value=Decimal(str(data.get('price_in_purchased_currency'))).quantize(Decimal('0.000001'))
            if isinstance(currency,str) and re.fullmatch('[A-Z]{3}',currency) and value.is_finite() and 0<=value<Decimal('1000000000000'):
                if row.amount is None:
                    row.amount=value;row.currency=currency
        except (InvalidOperation,ValueError): pass
    at=stamp(data.get('event_timestamp_ms'))
    if at and kind in LIFECYCLE and (row.lifecycle_at is None or at>row.lifecycle_at):
        row.lifecycle=kind;row.lifecycle_at=at
    refund = kind=='CANCELLATION' and (is_topup or data.get('cancel_reason')=='CUSTOMER_SUPPORT')
    if at and (refund or kind=='REFUND_REVERSED') and (row.refund_event_at is None or at>row.refund_event_at):
        row.refund_state='refunded' if refund else 'reversed';row.refund_event_at=at
    row.save()
