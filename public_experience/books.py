"""Local preview of explicitly selected published books. Never grants paid content globally."""
import ipaddress
import json
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from django.core.cache import cache
from diary_presets.models import Template
from diary_presets import storage
from .views import catalogue


def allowed(request):
    host = request.get_host().split(':')[0]
    try:
        return ipaddress.ip_address(host).is_private and ipaddress.ip_address(request.META.get('REMOTE_ADDR','')).is_private
    except ValueError:
        return host == 'localhost' and request.META.get('REMOTE_ADDR') in ('127.0.0.1','::1')


def rows(request):
    # Local development selections are deliberately unavailable on production domain.
    if not allowed(request):
        raise Http404()
    return Template.objects.filter(active=True, audience='public', series__active=True, current__isnull=False).select_related('current', 'series')


def version(request, pk, number):
    book = get_object_or_404(rows(request), pk=pk)
    return book, get_object_or_404(book.versions, number=number)


def preview(snap, page, small=False):
    path=page['preview']['thumbnailPath' if small else 'largePath']
    return storage.sign(snap['keys'][path])


@require_GET
def books(request):
    items=[]
    theme_order = {'生日纪念': 0, '爱情故事': 1, '亲子时光': 2, '山野自然': 3, '城市漫游': 4}
    for b in rows(request):
        series_title = b.series.title
        theme = {'爱情纪念': '爱情故事'}.get(series_title, series_title)
        s=b.current.snapshot
        p=next((p['data'] for p in s['pages'] if p['data']['id']==s['manifest']['coverPageID']),None)
        if p:
            items.append(dict(id=str(b.id), title=b.title, version=b.current.number, kind=b.content_kind, pageCount=len(s['pages']), cover=preview(s,p,True), theme=theme, position=theme_order.get(theme, 4), previewUnits=[u for u in s['manifest'].get('readingUnits',[]) if u.get('kind')=='spread'][:2]))
    return JsonResponse(dict(items=sorted(items,key=lambda b:b['position']), localPreview=True))


@require_GET
def browse(request, pk, number):
    b,v=version(request,pk,number);s=v.snapshot;m=s['manifest']
    units=m.get('readingUnits',[])
    if not units: raise Http404('模板尚无阅读单元')
    return JsonResponse(dict(id=str(b.id),title=b.title,version=v.number,units=units,
        pages=[dict(id=p['data']['id'],title=p['data']['title'],size=p['data']['size'],slots=p['data'].get('editableSlots',[])) for p in s['pages']]))


@require_GET
def page_preview(request,pk,number,page_id):
    _,v=version(request,pk,number);s=v.snapshot
    p=next((p['data'] for p in s['pages'] if p['data']['id']==page_id),None)
    if not p: raise Http404()
    return JsonResponse(dict(url=preview(s,p,request.GET.get('small')=='1')))


@require_GET
def projection(request,pk,number,page_id):
    _,v=version(request,pk,number);s=v.snapshot;m=s['manifest']
    p=next((p['data'] for p in s['pages'] if p['data']['id']==page_id),None)
    if not p: raise Http404()
    objects={};assets={};bucket=storage.bucket()
    def visit(oid,depth=0):
        if oid in objects:return
        if depth>32 or len(objects)>=200:raise ValueError('Object limit')
        path=m['objectTable'][oid];path=path if isinstance(path,str) else path['path']
        key=s['keys'][path]
        ck='web-object:'+key
        data=cache.get(ck)
        if data is None:
            data=json.loads(bucket.get_object(key).read(2*1024*1024));cache.set(ck,data,3600)
        objects[oid]=data
        if data.get('drawingPath'):raise ValueError('原生绘画尚不支持')
        for layer in data.get('layers',[]):
            if layer.get('contentID'):visit(layer['contentID'],depth+1)
            aid=layer.get('assetID')
            if aid:
                a=m['assetTable'][aid];assets[aid]=dict(url=bucket.sign_url('GET',s['keys'][a['path']],900,slash_safe=True,params={'x-oss-process':'image/resize,l_2048'}),pixelSize=a['pixelSize'])
    try:visit(p['rootContentID'])
    except (ValueError,KeyError):return JsonResponse({'message':'当前页尚不支持照片替换，请使用其他页面'},status=422)
    return JsonResponse(dict(page=p,objects=objects,assets=assets))


@require_GET
def slots(request, pk, number, page_id):
    """Resolve only current page's photo thumbnails, never its full image bundle."""
    _, v = version(request, pk, number)
    snap = v.snapshot
    page = next((p['data'] for p in snap['pages'] if p['data']['id'] == page_id), None)
    if not page:
        raise Http404()
    requested = {s['layerID'] for s in page.get('editableSlots', []) if s.get('kind') == 'photo'}
    found = {}
    visited = set()
    bucket = storage.bucket()
    def visit(oid, depth=0):
        if oid in visited or requested.issubset(found):
            return
        if depth > 32 or len(visited) >= 200:
            raise ValueError('Object limit')
        visited.add(oid)
        path = snap['manifest']['objectTable'][oid]
        path = path if isinstance(path, str) else path['path']
        key = snap['keys'][path]
        data = cache.get('web-object:' + key)
        if data is None:
            data = json.loads(bucket.get_object(key).read(2 * 1024 * 1024))
            cache.set('web-object:' + key, data, 3600)
        for layer in data.get('layers', []):
            if layer.get('id') in requested and layer.get('assetID'):
                asset = snap['manifest']['assetTable'][layer['assetID']]
                asset_key = snap['keys'][asset['path']]
                # The key is a member of the already authorized version's asset table.
                found[layer['id']] = bucket.sign_url('GET', asset_key, 900, slash_safe=True,
                    params={'x-oss-process': 'image/resize,w_160'})
            if layer.get('contentID'):
                visit(layer['contentID'], depth + 1)
    try:
        visit(page['rootContentID'])
    except (KeyError, ValueError):
        return JsonResponse({'message': '照片缩略图暂不可用'}, status=422)
    response = JsonResponse({'items': [{'layerId': key, 'url': url} for key, url in found.items()]})
    response['Cache-Control'] = 'private, max-age=300'
    return response
