"""RevenueCat transport: no automatic POST retry, no secrets in exceptions/logs."""
from dataclasses import dataclass
from urllib.parse import quote
import httpx
from django.conf import settings

@dataclass
class ProviderResult:
    status: int
    body: dict
    retry_after: int = 30

class RevenueCat:
    def request(self, method, path, *, body=None, key=None):
        secret = settings.REVENUECAT_V2_SECRET
        if not secret:
            return ProviderResult(503, {'type':'provider_not_configured'})
        headers = {'Authorization':'Bearer '+secret, 'Content-Type':'application/json'}
        if key:
            headers['Idempotency-Key'] = str(key)
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                response = client.request(method, 'https://api.revenuecat.com/v2/projects/'+quote(settings.REVENUECAT_PROJECT_ID,safe='')+path, headers=headers, json=body)
            try:
                data = response.json()
                if not isinstance(data,dict): raise ValueError()
            except ValueError:
                return ProviderResult(502, {'type':'invalid_response'})
            try: delay = max(3,min(3600,int(response.headers.get('Retry-After','30'))))
            except ValueError: delay = 30
            return ProviderResult(response.status_code,data,delay)
        except httpx.HTTPError:
            return ProviderResult(0, {'type':'transport_unknown'})

    def customer(self, identity):
        return self.request('GET',f'/customers/{identity.rc_app_user_id}')

    def subscriptions(self, identity):
        return self.request('GET',f'/customers/{identity.rc_app_user_id}/subscriptions?environment={identity.wallet_domain}&limit=100')

    def balance(self, identity):
        return self.request('GET',f'/customers/{identity.rc_app_user_id}/virtual_currencies?include_empty_balances=true')

    def transact(self, operation):
        return self.request('POST',f'/customers/{operation.identity.rc_app_user_id}/virtual_currencies/transactions?include_empty_balances=true',body=operation_body(operation),key=operation.rc_idempotency_key)

def operation_body(operation):
    return {'adjustments':{'DIAMOND':operation.delta},'reference':operation.reference}

def diamond_balance(body):
    for row in body.get('items',[]):
        if row.get('currency_code') == 'DIAMOND' and type(row.get('balance')) is int and row['balance'] >= 0:
            return row['balance']
    # Missing currency is not evidence of a zero balance.
    raise ValueError('Missing DIAMOND balance')
