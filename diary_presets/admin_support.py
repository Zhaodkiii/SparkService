from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission
from .models import Template
from . import storage

class Conflict(APIException):
    status_code = 409
    default_detail = '内容已修改，请刷新后重试'

class PresetAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_active and
                    (request.user.is_superuser or request.user.has_perm('diary_presets.change_template')))

def lock_template(pk, data):
    obj = get_object_or_404(Template.objects.select_for_update(), pk=pk, audience='public',deleted_at__isnull=True)
    if data.get('revision') != obj.revision:
        raise Conflict()
    return obj

def preview(key):
    return storage.sign(key) if key else None
