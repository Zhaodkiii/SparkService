"""Immutable encrypted channel versions. Never return plaintext secrets to administrators."""
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from rest_framework.exceptions import ValidationError
from .domain import Unavailable

SECRET_FIELDS = {'PRIVATE_KEY', 'PUBLIC_KEY', 'API_V3_KEY'}
PUBLIC_FIELDS = {'APPID', 'MCHID', 'SERIAL', 'PUBLIC_KEY_ID', 'NOTIFY_URL', 'SELLER_ID'}


def cipher():
    key = os.getenv('PRINT_PAYMENT_ENCRYPTION_KEY', '')
    if not key:
        path=Path(os.getenv('PRINT_PAYMENT_ENCRYPTION_KEY_FILE',str(settings.BASE_DIR / '.secrets' / 'print-payment.key')))
        try: key=path.read_text().strip()
        except OSError: pass
    if not key: raise Unavailable('请配置独立的 PRINT_PAYMENT_ENCRYPTION_KEY 后再保存支付密钥')
    try: return Fernet(key.encode())
    except ValueError: raise Unavailable('支付密钥存储配置无效')


def encrypt(data): return cipher().encrypt(json.dumps(data).encode()).decode()

def secrets(version):
    try: return json.loads(cipher().decrypt(version.encrypted.encode()))
    except (InvalidToken, ValueError): raise Unavailable('支付密钥无法解密，请检查部署配置')

def config(version):
    data=secrets(version)
    for field in ('PRIVATE_KEY','PUBLIC_KEY'):
        if data.get(field): data[field]=material(field,data[field])[0]
    return {**version.public, **data, 'ENVIRONMENT':version.environment}


def material(field, raw):
    """Accept provider copy/paste strings and PEM; never echo key contents."""
    import base64
    raw=raw.strip().replace('\\n','\n')
    try:
        if field=='API_V3_KEY':
            if len(raw.encode())!=32: raise ValueError()
            return raw, {'configured':True,'valid':True,'kind':'API v3'}
        private=field=='PRIVATE_KEY'
        if '-----BEGIN' in raw:
            key=serialization.load_pem_private_key(raw.encode(),password=None) if private else serialization.load_pem_public_key(raw.encode())
        else:
            data=base64.b64decode(''.join(raw.split()),validate=True)
            key=serialization.load_der_private_key(data,password=None) if private else serialization.load_der_public_key(data)
        expected=rsa.RSAPrivateKey if private else rsa.RSAPublicKey
        if not isinstance(key,expected) or key.key_size<2048: raise ValueError()
        pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()) if private else key.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        return pem.decode(), {'configured':True,'valid':True,'bits':key.key_size,'kind':'RSA'}
    except (ValueError,TypeError):
        raise ValidationError({field:'请填写 32 字节 API v3 密钥' if field=='API_V3_KEY' else '请填写有效的 RSA 密钥（至少 2048 位）；支持完整 PEM 或直接复制的密钥字符串'})


def statuses(version):
    data=secrets(version)
    result={}
    for field in ('PRIVATE_KEY','PUBLIC_KEY') + (('API_V3_KEY',) if version.channel_id=='wechat' else ()):
        raw=data.get(field,'')
        try: result[field]=material(field,raw)[1] if raw else {'configured':False,'valid':False}
        except ValidationError: result[field]={'configured':True,'valid':False}
    return result


def validate(channel, public, private, environment):
    from urllib.parse import urlparse
    required={'APPID','NOTIFY_URL'} | ({'MCHID','SERIAL','PUBLIC_KEY_ID'} if channel=='wechat' else {'SELLER_ID'})
    errors={k:'此项必填' for k in required if not str(public.get(k,'')).strip()}
    if environment not in ('production','sandbox') or channel not in ('wechat','alipay'): errors['environment']='渠道或环境无效'
    if channel=='wechat' and environment!='production': errors['environment']='微信当前仅支持正式环境'
    if public.get('NOTIFY_URL'):
        parsed=urlparse(public['NOTIFY_URL']);expected='/api/v1/print/'+channel+'-notify/'
        if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.query or parsed.fragment or parsed.path!=expected: errors['NOTIFY_URL']='请填写公网 HTTPS 地址，路径须为 '+expected
    if channel=='alipay':
        if not str(public.get('APPID','')).isdigit() or len(str(public.get('APPID','')))!=16: errors['APPID']='AppID 应为 16 位数字'
        if not str(public.get('SELLER_ID','')).isdigit() or len(str(public.get('SELLER_ID','')))!=16: errors['SELLER_ID']='商家 PID 应为 16 位数字'
    normalized=dict(private)
    for field in ('PRIVATE_KEY','PUBLIC_KEY') + (('API_V3_KEY',) if channel=='wechat' else ()):
        if not private.get(field): errors[field]='尚未配置，请填写'
        else:
            try: normalized[field]=material(field,private[field])[0]
            except ValidationError as exc: errors.update(exc.detail)
    if errors: raise ValidationError(errors)
    return normalized
