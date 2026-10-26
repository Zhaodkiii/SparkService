"""微信支付 API v3 普通商户 APP 支付。响应与通知均验签，密钥仅服务端持有。"""
from contextvars import ContextVar

active_config = ContextVar("print_wechat_config", default=None)

import base64
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from .domain import Unavailable


def config():
    if active_config.get() is not None: return active_config.get()
    values = {k: getattr(settings, 'PRINT_WXPAY_' + k, '') for k in (
        'APPID', 'MCHID', 'SERIAL', 'PRIVATE_KEY_PATH', 'PUBLIC_KEY_ID', 'PUBLIC_KEY_PATH', 'API_V3_KEY', 'NOTIFY_URL')}
    if not all(values.values()) or len(values['API_V3_KEY'].encode()) != 32 or not values['NOTIFY_URL'].startswith('https://'):
        raise Unavailable('微信支付尚未配置，请稍后再试')
    return values


def sign(message, cfg):
    try:
        key = serialization.load_pem_private_key(cfg['PRIVATE_KEY'].encode() if 'PRIVATE_KEY' in cfg else Path(cfg['PRIVATE_KEY_PATH']).read_bytes(), password=None)
        return base64.b64encode(key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()
    except (OSError, ValueError):
        raise Unavailable('微信支付证书配置不可用')


def verify(headers, body, cfg):
    try:
        # requests headers 不区分大小写；Django request.headers 同样如此。
        stamp, nonce = headers['Wechatpay-Timestamp'], headers['Wechatpay-Nonce']
        if abs(time.time() - int(stamp)) > 300 or headers['Wechatpay-Serial'] != cfg['PUBLIC_KEY_ID']:
            raise ValueError('signature timestamp or key mismatch')
        key = serialization.load_pem_public_key(cfg['PUBLIC_KEY'].encode() if 'PUBLIC_KEY' in cfg else Path(cfg['PUBLIC_KEY_PATH']).read_bytes())
        key.verify(base64.b64decode(headers['Wechatpay-Signature'], validate=True),
                   f'{stamp}\n{nonce}\n'.encode() + body + b'\n', padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        raise ValueError('微信支付签名验证失败') from exc


def request(method, path, payload=None):
    cfg = config()
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) if payload is not None else ''
    stamp, nonce = str(int(time.time())), secrets.token_hex(16)
    signature = sign(f'{method}\n{path}\n{stamp}\n{nonce}\n{body}\n', cfg)
    auth = f'WECHATPAY2-SHA256-RSA2048 mchid="{cfg["MCHID"]}",nonce_str="{nonce}",timestamp="{stamp}",serial_no="{cfg["SERIAL"]}",signature="{signature}"'
    try:
        response = requests.request(method, 'https://api.mch.weixin.qq.com' + path,
            data=body.encode() if body else None, timeout=(5, 20), allow_redirects=False,
            headers={'Authorization':auth, 'Content-Type':'application/json', 'Accept':'application/json',
                     'Wechatpay-Serial':cfg['PUBLIC_KEY_ID']})
        verify(response.headers, response.content, cfg)
        if response.status_code not in (200, 201, 204):
            code = response.json().get('code', '')
            if code == 'ORDER_NOT_EXIST': return {'trade_state':'NOT_EXIST'}
            if code in ('RESOURCE_NOT_EXISTS','REFUND_NOT_EXIST') and method=='GET' and '/refund/' in path: return {'refund_absent':True}
            from .payment_errors import GatewayError
            if code in ('NOTENOUGH','ACCOUNT_ERROR','USER_ACCOUNT_ABNORMAL'):
                raise GatewayError(code,'balance','微信商户退款资金不足或账户受限','请核对微信商户可用退款资金及账户状态后重试')
            if code in ('NO_AUTH','SIGN_ERROR'):
                raise GatewayError(code,'permission','微信商户权限或签名配置异常','请核对商户授权和当前交易配置后恢复处理')
            raise Unavailable('微信支付处理未完成，请刷新订单后重试')
        return response.json() if response.content else {}
    except (requests.RequestException, ValueError):
        raise Unavailable('微信支付结果暂未确认，请稍后刷新订单')


def app_parameters(prepay_id):
    cfg = config()
    stamp, nonce = str(int(time.time())), secrets.token_hex(16)
    return dict(appid=cfg['APPID'], partnerid=cfg['MCHID'], prepayid=prepay_id, package='Sign=WXPay',
                noncestr=nonce, timestamp=int(stamp), sign=sign(f'{cfg["APPID"]}\n{stamp}\n{nonce}\n{prepay_id}\n', cfg))


def create(order):
    cfg = config()
    return request('POST', '/v3/pay/transactions/app', dict(appid=cfg['APPID'], mchid=cfg['MCHID'],
        description=('手帐印制 · ' + order.title)[:100], out_trade_no=order.id.hex,
        time_expire=order.payment_expires_at.isoformat(), notify_url=cfg['NOTIFY_URL'],
        amount=dict(total=order.total_fen, currency='CNY')))['prepay_id']


def query(order):
    return request('GET', f'/v3/pay/transactions/out-trade-no/{order.id.hex}?' + urlencode({'mchid':config()['MCHID']}))


def close(order):
    return request('POST', f'/v3/pay/transactions/out-trade-no/{order.id.hex}/close', {'mchid':config()['MCHID']})


def refund(order):
    return request('POST', '/v3/refund/domestic/refunds', dict(out_trade_no=order.id.hex,
        out_refund_no=getattr(order, 'refund_number', 'R' + order.id.hex), reason=order.refund_reason or '订单取消',
        amount=dict(refund=order.total_fen, total=order.total_fen, currency='CNY')))


def query_refund(order):
    return request('GET', '/v3/refund/domestic/refunds/' + getattr(order, 'refund_number', 'R' + order.id.hex))


def notification(headers, body):
    cfg = config()
    verify(headers, body, cfg)
    resource = json.loads(body)['resource']
    if resource['algorithm'] != 'AEAD_AES_256_GCM': raise ValueError('Invalid encryption')
    plain = AESGCM(cfg['API_V3_KEY'].encode()).decrypt(resource['nonce'].encode(),
        base64.b64decode(resource['ciphertext']), resource.get('associated_data', '').encode())
    return json.loads(plain)
