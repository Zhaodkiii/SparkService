"""Observe provider grants; never add purchased currency from our own database."""
import hashlib
from datetime import datetime,timezone as utc
from django.conf import settings
from django.utils import timezone
from .models import RechargeProduct,TopUpRecord,ReconciliationCase

def observe(identity,data,amount=None):
    product=RechargeProduct.objects.filter(rc_project_id=identity.rc_project_id,apple_product_id=data.get('product_id')).first()
    if not product: return None
    tx=data.get('transaction_id');store=data.get('store')
    if not isinstance(tx,str) or not tx or len(tx)>2048 or store!='APP_STORE': return False
    row,_=TopUpRecord.objects.get_or_create(store=store,app_id=settings.REVENUECAT_APP_ID,purchase_environment=identity.wallet_domain,transaction_digest=hashlib.sha256(tx.encode()).hexdigest(),defaults={'identity':identity,'store_transaction_id':tx,'original_transaction_id':str(data.get('original_transaction_id') or ''),'recharge_product':product,'expected_units':product.units})
    if row.identity_id!=identity.pk or row.recharge_product_id!=product.pk:
        ReconciliationCase.objects.get_or_create(identity=identity,kind='topup_identity_or_product_conflict',evidence={'topup_id':str(row.pk)})
        return False
    stamp=data.get('purchased_at_ms')
    if type(stamp) is int:
        try: row.purchased_at=datetime.fromtimestamp(stamp/1000,utc.utc)
        except (ValueError,OverflowError,OSError): return False
    if amount is not None:
        # A delayed original grant cannot erase an already observed refund.
        if amount>0 and row.state in ('refunded','refund_observed'):
            return row
        row.verified_units=amount
        if amount>0 and amount!=row.expected_units:
            row.state='unknown';row.save()
            ReconciliationCase.objects.get_or_create(identity=identity,kind='topup_units_mismatch',evidence={'topup_id':str(row.pk),'expected':row.expected_units,'observed':amount})
            return False
        row.state='granted' if amount>0 else 'refunded'
        row.grant_confirmed_at=timezone.now()
    elif data.get('type')=='CANCELLATION':
        if row.state!='refunded': row.state='refund_observed'
    elif row.state=='purchase_observed': row.state='grant_pending'
    row.save()
    return row
