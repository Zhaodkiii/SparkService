"""Metadata-only OSS confirmation. Never read, decode, or proxy image bodies."""
import base64
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError, APIException
from rest_framework import serializers
from diary_presets.storage import bucket, prefix
from .models import MaterialUpload, ResourceBlob


class StorageUnavailable(APIException):
    status_code = 503
    default_detail = 'OSS 暂不可用，请重试确认；已上传文件无需重传'


def upload_status():
    if not settings.MATERIAL_UPLOADS_ENABLED:
        return False, '管理员已关闭素材上传，请启用 MATERIAL_UPLOADS_ENABLED'
    if not all(getattr(settings, name, '') for name in (
        'ALIYUN_ACCESS_KEY_ID', 'ALIYUN_ACCESS_KEY_SECRET', 'ALIYUN_OSS_ENDPOINT', 'ALIYUN_OSS_BUCKET'
    )):
        return False, 'OSS 连接配置不完整，请配置现有业务服务的 OSS 访问权限和地址'
    return True, ''


def metadata(value, purpose, thumbnail=False):
    if not isinstance(value, dict): raise ValidationError('请升级后台页面，提交原图和本地生成的缩略图信息')
    size=serializers.IntegerField(min_value=1,max_value=1024*1024 if thumbnail else (10 if purpose=='sticker' else 15)*1024*1024).run_validation(value.get('byte_size'))
    maximum=256 if thumbnail else 4096 if purpose=='sticker' else 8192
    width=serializers.IntegerField(min_value=1,max_value=maximum).run_validation(value.get('width'))
    height=serializers.IntegerField(min_value=1,max_value=maximum).run_validation(value.get('height'))
    if width*height>(16_000_000 if purpose=='sticker' else 24_000_000): raise ValidationError('图片总像素超限')
    allowed=('image/png',) if thumbnail else ('image/png','image/webp') if purpose=='sticker' else ('image/png','image/webp','image/jpeg')
    mime=value.get('mime')
    if mime not in allowed: raise ValidationError('图片类型不符合要求')
    digest=value.get('sha256','')
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest): raise ValidationError('无效 SHA-256')
    try:
        md5=base64.b64decode(value.get('md5',''),validate=True)
        if len(md5)!=16: raise ValueError()
    except (ValueError,TypeError): raise ValidationError('无效 Content-MD5')
    if not thumbnail:
        if value.get('has_visible_pixels') is not True: raise ValidationError('图片没有可见内容')
        if purpose=='sticker' and value.get('has_transparency') is not True: raise ValidationError('贴纸必须包含实际透明像素')
        if purpose=='cover' and (width!=height or width<512): raise ValidationError('封面须为至少 512×512 方图')
        if purpose=='preview' and width<750: raise ValidationError('展示图宽度至少 750 像素')
    return dict(byte_size=size,width=width,height=height,mime=mime,sha256=digest,md5=base64.b64encode(md5).decode())


def upload_plan(upload):
    oss=bucket()
    result={}
    for part in ('original','thumbnail'):
        info=upload.upload_metadata[part]
        key=upload.object_key if part=='original' else upload.object_key+'/thumbnail'
        headers={'Content-Type':info['mime'],'Content-MD5':info['md5']}
        result[part]=dict(url=oss.sign_url('PUT',key,3600,headers=headers,slash_safe=True),headers=headers)
    return result


def _verify_head(oss, key, info):
    head=oss.head_object(key)
    expected=base64.b64decode(info['md5']).hex()
    # Signed single PUT uses Content-MD5; ETag must match that same body checksum.
    if head.content_length!=info['byte_size'] or head.etag.strip('"').lower()!=expected:
        raise ValidationError('OSS 文件大小或校验和不一致，请重新选择文件上传')
    if head.content_type.split(';',1)[0].lower()!=info['mime']:
        raise ValidationError('OSS 文件类型与上传声明不一致')
    return head


@transaction.atomic
def confirm_upload(pk, actor):
    from django.shortcuts import get_object_or_404
    upload=get_object_or_404(MaterialUpload.objects.select_for_update(),pk=pk,actor=actor)
    if upload.state=='verified': return upload
    if not upload.upload_metadata:
        raise ValidationError('这是旧版上传会话，请重新选择图片，浏览器将生成缩略图后直接上传')
    oss=bucket()
    resources={}
    try:
        for part in ('original','thumbnail'):
            info=upload.upload_metadata[part]
            source=upload.object_key if part=='original' else upload.object_key+'/thumbnail'
            head=_verify_head(oss,source,info)
            existing=ResourceBlob.objects.filter(pk=info['sha256']).first()
            if existing:
                if (existing.byte_size,existing.width,existing.height,existing.mime)!=(info['byte_size'],info['width'],info['height'],info['mime']):
                    raise ValidationError('资源摘要与已有素材属性冲突，请重新选择图片')
                _verify_head(oss,existing.object_key,info)
                resources[part]=existing
                continue
            # Session-specific destination is never writable by the browser's signed URL.
            # Source ETag condition prevents replacement between HEAD and COPY.
            target=prefix()+f'blobs/material-uploads/{upload.pk}/{part}'
            oss.copy_object(settings.ALIYUN_OSS_BUCKET,source,target,headers={
                'x-oss-copy-source-if-match':head.etag,
                'x-oss-metadata-directive':'REPLACE','Content-Type':info['mime'],
            })
            _verify_head(oss,target,info)
            blob,created=ResourceBlob.objects.get_or_create(sha256=info['sha256'],defaults=dict(
                object_key=target,byte_size=info['byte_size'],width=info['width'],height=info['height'],mime=info['mime']))
            if not created and (blob.byte_size,blob.width,blob.height,blob.mime)!=(info['byte_size'],info['width'],info['height'],info['mime']):
                raise ValidationError('资源摘要与已有素材属性冲突，请重新选择图片')
            if not created and blob.object_key!=target:
                _verify_head(oss,blob.object_key,info)
                # A concurrent confirmation won deduplication. Remove only our unused copy.
                oss.delete_object(target)
            resources[part]=blob
    except ValidationError: raise
    except Exception as exc:
        # Do not include OSS errors, credentials or signed URLs in API messages.
        if getattr(exc,'status',None)==404:
            raise ValidationError('原图或缩略图尚未上传完整，请完成两张图片的上传后重试') from None
        raise StorageUnavailable() from None
    upload.resource=resources['original'];upload.thumbnail=resources['thumbnail']
    upload.state='verified';upload.error='';upload.save()
    return upload
