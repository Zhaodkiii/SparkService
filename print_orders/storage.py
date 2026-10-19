"""印制服务只离线签名。所有 OSS 请求由客户端或管理员浏览器直接发起。"""
import math
from django.conf import settings
from diary_presets.storage import bucket

PART_SIZE = 5 * 1024 * 1024
PART_HEADERS = {'Content-Type': 'application/octet-stream'}
INIT_HEADERS = {'Content-Type': 'application/pdf', 'x-oss-object-acl': 'private'}
COMPLETE_HEADERS = {'Content-Type': 'application/xml'}


def prefix():
    return getattr(settings, 'PRINT_OSS_PREFIX', 'traveldiary/print/').strip('/') + '/'


def staging(production, role):
    return f'{prefix()}staging/{production.id}/{role}.pdf'


def download(key):
    if not key.startswith((prefix()+'staging/', prefix()+'production/')):
        raise ValueError('Invalid print key')
    return bucket().sign_url('GET', key, 300, slash_safe=True)


def multipart_plan(production):
    signer = bucket()  # 构造签名器不发送网络请求。
    plans = []
    for f in production.manifest:
        key = staging(production, f['role'])
        upload_id = production.uploads.get(f['role'], {}).get('id')
        def signed(method, params=None, headers=None):
            return signer.sign_url(method, key, 900, params=params, headers=headers, slash_safe=True)
        parts = []
        if upload_id:
            for number in range(1, math.ceil(f['size']/PART_SIZE)+1):
                offset = (number-1)*PART_SIZE
                parts.append(dict(number=number,offset=offset,size=min(PART_SIZE,f['size']-offset),headers=PART_HEADERS,
                    url=signed('PUT', {'uploadId':upload_id,'partNumber':str(number)}, PART_HEADERS)))
        plans.append(dict(role=f['role'], upload_id=upload_id, parts=parts,
            init_url=signed('POST', {'uploads':''}, INIT_HEADERS), init_headers=INIT_HEADERS,
            list_url=signed('GET', {'uploadId':upload_id}) if upload_id else None,
            complete_url=signed('POST', {'uploadId':upload_id}, COMPLETE_HEADERS) if upload_id else None,
            complete_headers=COMPLETE_HEADERS, head_url=signed('HEAD')))
    return plans


def accept_client_upload(order):
    """仅登记客户端完成通知，不下载、HEAD、检查或合并 OSS 文件。"""
    p = order.current_production
    p.state = 'ready'; p.error = ''; p.lease = None; p.lease_until = None
    p.result = {'files': {f['role']:dict(key=staging(p,f['role']),sha256=f['sha256'],size=f['size']) for f in p.manifest},
                'checks':['客户端已检查并确认生产稿，等待人工印前审核']}
    p.save()
    order.file_state = 'ready'
    if order.payment_state in ('paid', 'not_required'): order.state = 'awaiting_review'
