"""Bound JSON control-plane bodies before authentication, logging or parsing."""
import io
from django.http import JsonResponse


class MaterialControlPlaneGuard:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        sync=request.path.startswith(('/api/v1/material-sync/','/api/v1/font-sync/','/api/v1/preset-sync/'))
        materials=request.path.startswith(('/api/v1/materials/','/api/v1/fonts/','/api/admin/v1/content-sync/'))
        if (sync or materials) and request.method in ('POST','PATCH','PUT'):
            if request.content_type not in (('application/json',) if sync else ('application/json','')):
                return JsonResponse({'code':'metadata_only','message':'此接口仅接收 JSON 元数据，文件请直传 OSS'},status=415)
            limit=16*1024*1024 if request.path.startswith('/api/v1/preset-sync/') else (2*1024*1024 if sync else 262144)
            try:size=int(request.META.get('CONTENT_LENGTH') or 0)
            except ValueError:size=limit+1
            if size>limit:return self.too_large()
            # Also bound streams without a trustworthy Content-Length.
            body=request.read(limit+1)
            if len(body)>limit:return self.too_large()
            request._body=body
            request._stream=io.BytesIO(body)
        return self.get_response(request)
    @staticmethod
    def too_large():
        return JsonResponse({'code':'metadata_too_large','message':'元数据超过接口限制，请拆分内容；文件必须直传 OSS'},status=413)
