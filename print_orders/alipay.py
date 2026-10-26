"""Alipay APP payments, RSA2 public-key mode; verify the original response JSON bytes."""
import base64
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from .domain import Unavailable
from .payment_errors import alipay_error


def canonical(values):
    return '&'.join(f'{k}={values[k]}' for k in sorted(values) if k not in ('sign','sign_type') and values[k] not in ('',None))


def verify(text, signature, cfg):
    try:
        key=serialization.load_pem_public_key(cfg['PUBLIC_KEY'].encode())
        key.verify(base64.b64decode(signature,validate=True),text.encode(),padding.PKCS1v15(),hashes.SHA256())
    except Exception as exc: raise ValueError('支付宝签名验证失败') from exc


def parameters(method, biz, cfg, notify=False):
    values={'app_id':cfg['APPID'],'method':method,'format':'JSON','charset':'utf-8','sign_type':'RSA2',
            'timestamp':datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'),
            'version':'1.0','biz_content':json.dumps(biz,ensure_ascii=False,separators=(',',':'))}
    if notify: values['notify_url']=cfg['NOTIFY_URL']
    text='&'.join(f'{k}={values[k]}' for k in sorted(values))
    key=serialization.load_pem_private_key(cfg['PRIVATE_KEY'].encode(),password=None)
    values['sign']=base64.b64encode(key.sign(text.encode(),padding.PKCS1v15(),hashes.SHA256())).decode()
    return values


def request(method, biz, cfg):
    endpoint='https://openapi.alipay.com/gateway.do' if cfg['ENVIRONMENT']=='production' else 'https://openapi-sandbox.dl.alipaydev.com/gateway.do'
    try:
        # Alipay must know the charset before decoding POST fields containing Chinese.
        # Keep charset in the signed fields and declare it in the gateway URL too.
        response=requests.post(endpoint,params={'charset':'utf-8'},data=parameters(method,biz,cfg),
                               headers={'Content-Type':'application/x-www-form-urlencoded; charset=utf-8'},
                               timeout=(5,20),allow_redirects=False)
        response.raise_for_status()
        raw=response.content.decode('utf-8'); envelope=json.loads(raw)
        name=method.replace('.','_')+'_response'
        # Locate and decode the original value, preserving signed spacing and escaping.
        decoder=json.JSONDecoder(); pos=raw.index('{')+1; signed=None
        while pos<len(raw):
            while raw[pos].isspace() or raw[pos]==',': pos+=1
            if raw[pos]=='}': break
            key,end=decoder.raw_decode(raw,pos); pos=end
            while raw[pos].isspace(): pos+=1
            if raw[pos]!=':': raise ValueError('Invalid response')
            pos+=1
            while raw[pos].isspace(): pos+=1
            value,end=decoder.raw_decode(raw,pos)
            if key==name: signed=raw[pos:end]
            pos=end
        if signed is None: raise ValueError('Missing response')
        verify(signed,envelope['sign'],cfg)
        data=envelope[name]
        if data.get('code')!='10000':
            if data.get('sub_code')=='ACQ.TRADE_NOT_EXIST': return {'trade_status':'NOT_EXIST'}
            raise alipay_error(data.get('sub_code','ALIPAY_BUSINESS_ERROR'))
        return data
    except (requests.RequestException,ValueError,KeyError,IndexError): raise Unavailable('支付宝结果暂未确认，请稍后刷新订单')


def money(fen): return f'{Decimal(fen)/100:.2f}'

def fen(value):
    try:
        n=Decimal(str(value))*100
        if not n.is_finite() or n!=n.to_integral_value() or n<0: raise ValueError()
        return int(n)
    except (InvalidOperation,ValueError): raise ValueError('Invalid amount')


def create(attempt, cfg):
    biz={'out_trade_no':attempt.id.hex,'total_amount':money(attempt.amount),'subject':('手帐印制 · '+attempt.order.title)[:100],
         'product_code':'QUICK_MSECURITY_PAY','seller_id':cfg['SELLER_ID'],
         'time_expire':attempt.expires_at.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')}
    return urlencode(parameters('alipay.trade.app.pay',biz,cfg,notify=True))


def notification(values, cfg):
    if values.get('sign_type')!='RSA2': raise ValueError('Invalid sign type')
    verify(canonical(values),values.get('sign',''),cfg)
    if values.get('app_id')!=cfg['APPID'] or values.get('seller_id')!=cfg['SELLER_ID']: raise ValueError('Invalid merchant')
    return values
