"""Personal finished PNGs. File bodies travel directly between the device and OSS."""
import uuid
from django.conf import settings
from django.core import signing
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from diary_presets.storage import bucket
from .views import AuthView
from .models import UserSticker
from .direct_uploads import StorageUnavailable

MAX_BYTES = 10 * 1024 * 1024
SALT = 'personal-sticker-upload'


def root(user):
    environment = getattr(settings, 'USER_STICKER_OSS_ENV_PREFIX', '').strip('/')
    return (environment + '/' if environment else '') + f'user-content/stickers/{user.pk}/'


def payload(row):
    return dict(id=str(row.pk), imageObjectKey=row.image_object_key,
                createdAt=row.created_at.isoformat(),
                url=bucket().sign_url('GET', row.image_object_key, 900, slash_safe=True))


class Upload(AuthView):
    def post(self, request):
        identity = serializers.UUIDField().run_validation(request.data.get('uuid'))
        size = serializers.IntegerField(min_value=1, max_value=MAX_BYTES).run_validation(request.data.get('byte_size', request.data.get('byteSize')))
        key = root(request.user) + str(identity) + '.png'
        if UserSticker.objects.filter(owner=request.user, image_object_key=key).exists():
            raise ValidationError('贴纸已保存，请使用新的文件名')
        # A short-lived signed plan needs no pending business record.
        token = signing.dumps(dict(user=str(request.user.pk), key=key, size=size), salt=SALT)
        headers = {'Content-Type': 'image/png', 'x-oss-forbid-overwrite': 'true'}
        try:
            url = bucket().sign_url('PUT', key, 900, headers=headers, slash_safe=True)
        except Exception as exc:
            raise StorageUnavailable() from exc
        return Response(dict(imageObjectKey=key, url=url, headers=headers, token=token))


class Stickers(AuthView):
    def get(self, request):
        offset = serializers.IntegerField(min_value=0).run_validation(request.query_params.get('offset', 0))
        rows = list(UserSticker.objects.filter(owner=request.user)[offset:offset + 41])
        return Response(dict(items=[payload(row) for row in rows[:40]], next=offset + 40 if len(rows) > 40 else None))

    def post(self, request):
        try:
            plan = signing.loads(request.data.get('token', ''), salt=SALT, max_age=86400)
        except (signing.BadSignature, TypeError) as exc:
            raise ValidationError('上传授权已失效，请重新获取授权') from exc
        key = request.data.get('image_object_key', request.data.get('imageObjectKey'))
        if plan.get('user') != str(request.user.pk) or key != plan.get('key') or not key.startswith(root(request.user)):
            raise ValidationError('图片不属于当前用户')
        existing = UserSticker.objects.filter(owner=request.user, image_object_key=key).first()
        if existing:
            return Response(payload(existing))
        try:
            head = bucket().head_object(key)
        except Exception as exc:
            raise StorageUnavailable() from exc
        if head.content_length != plan['size'] or head.content_type.split(';')[0] != 'image/png':
            raise ValidationError('图片大小或类型不正确')
        row, _ = UserSticker.objects.get_or_create(owner=request.user, image_object_key=key)
        return Response(payload(row), status=201)


class StickerDetail(AuthView):
    def delete(self, request, pk):
        get_object_or_404(UserSticker, pk=pk, owner=request.user).delete()
        # Never delete the PNG: saved diary layers may still refer to it.
        return Response(status=204)
