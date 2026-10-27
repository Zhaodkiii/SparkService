"""Reject file bodies before request loggers or DRF parsers read them."""
from django.http import JsonResponse


class MaterialControlPlaneGuard:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        if request.path.startswith('/api/v1/materials/') and request.method in ('POST','PATCH','PUT'):
            if request.content_type not in ('application/json',''):
                return JsonResponse({'code':'metadata_only','message':'文件请直传 OSS，此接口仅接收 JSON 元数据'},status=415)
            try: size=int(request.META.get('CONTENT_LENGTH') or 0)
            except ValueError: size=262145
            if size>262144:
                return JsonResponse({'code':'metadata_too_large','message':'元数据请求超过 256 KiB，请将文件直传 OSS'},status=413)
        return self.get_response(request)
