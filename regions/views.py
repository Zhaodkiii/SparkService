import json
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_safe
from .models import RegionState, RegionDataset
from .dataset import sha, canonical


@require_safe
def manifest(request):
    state = RegionState.objects.select_related('current').filter(pk=1).first()
    if not state or not state.current or state.current.status != 'published':
        return JsonResponse({'code':'REGION_DATA_UNAVAILABLE'},status=503)
    data=state.current
    path=f'/api/v1/regions/datasets/{data.version}.json'
    url=(settings.REGIONS_CDN_BASE_URL.rstrip('/')+'/'+data.version+'.json') if settings.REGIONS_CDN_BASE_URL else path
    body=dict(schema_version=1, release_sequence=state.release_sequence, dataset_version=data.version,
        source=data.source,source_as_of=data.source_as_of.isoformat() if data.source_as_of else None,
        fetched_at=data.fetched_at.isoformat(),published_at=data.published_at.isoformat(),
        client_check_after_seconds=settings.REGIONS_CLIENT_CHECK_DAYS*86400,
        download_url=url,sha256=data.artifact_sha256,byte_size=len(data.artifact.encode()),
        capabilities=['structured_print_address_v1'])
    etag='"'+sha(canonical(body))+'"'
    response=HttpResponse(status=304) if request.headers.get('If-None-Match')==etag else JsonResponse(body)
    response['ETag']=etag; response['Cache-Control']='public, max-age=300, must-revalidate'
    return response


@require_safe
def dataset(request, version):
    data=get_object_or_404(RegionDataset,pk=version,status='published')
    response=HttpResponse(data.artifact,content_type='application/json; charset=utf-8')
    response['ETag']='"'+data.artifact_sha256+'"';response['Cache-Control']='public, max-age=31536000, immutable'
    return response
