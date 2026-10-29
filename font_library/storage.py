"""Control plane: only signatures, HEAD and conditional COPY. No body reads."""
import base64
from django.conf import settings
from rest_framework.exceptions import ValidationError
from diary_presets.storage import bucket

def prefix():
    value = settings.FONT_OSS_PREFIX.strip('/') + '/'
    if len(value) > 160:
        raise ValidationError('FONT_OSS_PREFIX 不能超过 160 字符，以确保生成的 OSS key 可安全建立索引')
    return value

def sign(key, method='GET', headers=None):
    if not key.startswith(prefix()) or '..' in key.split('/'):
        raise ValidationError('无效字体资源路径')
    return bucket().sign_url(method, key, 900, headers=headers or {}, slash_safe=True)

def verify(key, size, mime, md5=None):
    head = bucket().head_object(key)
    if head.content_length != size or head.content_type.split(';')[0].lower() != mime:
        raise ValidationError('OSS 文件大小或类型与上传计划不符')
    if md5 and head.etag.strip('"').lower() != base64.b64decode(md5).hex():
        raise ValidationError('OSS 传输校验失败')
    return head

def freeze(upload):
    head = verify(upload.object_key, upload.byte_size, upload.mime, upload.md5)
    target = prefix() + f'candidates/{upload.pk}/resource'
    bucket().copy_object(settings.ALIYUN_OSS_BUCKET, upload.object_key, target, headers={
        'x-oss-copy-source-if-match': head.etag,
        'x-oss-metadata-directive': 'REPLACE', 'Content-Type': upload.mime,
    })
    frozen = verify(target, upload.byte_size, upload.mime, upload.md5)
    return target, frozen.etag
