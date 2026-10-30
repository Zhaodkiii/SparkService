"""Restricted service identity and pinned HTTPS transport."""
import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from urllib.parse import urlparse
import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from material_library.models import MaterialSyncNonce
from .sync_protocol import canonical, SyncError

PREFIX='/api/v1/preset-sync/'


def signature(secret, method, path, stamp, nonce, body):
    value='\n'.join([method.upper(),path,stamp,nonce,hashlib.sha256(body).hexdigest()])
    return hmac.new(secret.encode(),value.encode(),hashlib.sha256).hexdigest()


def authorize(request):
    if not settings.MATERIAL_SYNC_RECEIVER_ENABLED or settings.MATERIAL_SYNC_ENVIRONMENT_ID!='production':
        raise SyncError('RECEIVER_DISABLED','生产同步接收未启用')
    key=request.headers.get('X-Sync-Key','');record=settings.MATERIAL_SYNC_ACCEPTED_KEYS.get(key)
    if not isinstance(record,dict) or not record.get('secret') or not record.get('environment') or record['environment']=='production':raise SyncError('AUTH_FAILED','服务认证失败')
    stamp=request.headers.get('X-Sync-Time','');nonce=request.headers.get('X-Sync-Nonce','');supplied=request.headers.get('X-Sync-Signature','')
    try:
        if abs(time.time()-int(stamp))>300 or len(nonce)!=32:raise ValueError()
    except ValueError:raise SyncError('AUTH_FAILED','服务认证已过期')
    expected=signature(record['secret'],request.method,request.get_full_path(),stamp,nonce,request.body)
    if not hmac.compare_digest(expected,supplied):raise SyncError('AUTH_FAILED','服务认证失败')
    try:
        with transaction.atomic():MaterialSyncNonce.objects.create(digest=hashlib.sha256((key+':'+nonce).encode()).hexdigest(),expires_at=timezone.now()+timedelta(minutes=10))
    except IntegrityError:raise SyncError('AUTH_FAILED','请求已处理，请生成新的认证随机数')
    return record['environment']


def source_config():
    if not settings.MATERIAL_SYNC_SOURCE_ENABLED or not settings.MATERIAL_SYNC_ENVIRONMENT_ID or settings.MATERIAL_SYNC_ENVIRONMENT_ID=='production':return False,'当前环境未启用向生产同步'
    parsed=urlparse(settings.MATERIAL_SYNC_TARGET_BASE_URL)
    # Exact fixed deployment target; no browser-controlled URLs, userinfo, redirects or proxy inheritance.
    if parsed.scheme!='https' or parsed.hostname not in ('diary.dreamwhale.top','39.106.39.110') or parsed.port not in (None,443) or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username:return False,'生产同步地址未正确配置'
    if not settings.MATERIAL_SYNC_KEY_ID or not settings.MATERIAL_SYNC_SECRET:return False,'生产同步服务凭证未配置'
    return True,''


def remote(method,path,data=None):
    enabled,reason=source_config()
    if not enabled:raise SyncError('SOURCE_DISABLED',reason)
    body=canonical(data) if data is not None else b''
    stamp=str(int(time.time()));nonce=secrets.token_hex(16)
    headers={'Content-Type':'application/json','X-Sync-Key':settings.MATERIAL_SYNC_KEY_ID,'X-Sync-Time':stamp,'X-Sync-Nonce':nonce,
        'X-Sync-Signature':signature(settings.MATERIAL_SYNC_SECRET,method,PREFIX+path,stamp,nonce,body)}
    try:
        with requests.Session() as session:
            session.trust_env=False
            response=session.request(method,settings.MATERIAL_SYNC_TARGET_BASE_URL.rstrip('/')+PREFIX+path,data=body,headers=headers,timeout=(5,20),allow_redirects=False,stream=True)
            chunks=[];size=0
            for chunk in response.iter_content(16384):
                size+=len(chunk)
                if size>2*1024*1024:raise SyncError('TARGET_UNAVAILABLE','生产响应超过限制',True)
                chunks.append(chunk)
            result=json.loads(b''.join(chunks))
            if response.status_code>=300:raise SyncError(result.get('code','TARGET_UNAVAILABLE'),result.get('message','生产同步请求失败'),response.status_code>=500)
            return result
    except SyncError:raise
    except (requests.RequestException,ValueError):raise SyncError('TARGET_UNAVAILABLE','生产服务暂时不可达，正在确认处理结果',True)
