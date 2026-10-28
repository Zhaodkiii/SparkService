"""Anonymous Web catalogue. Only explicitly approved Web manifests are served."""
import json
from pathlib import Path
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def catalogue():
    path = Path(settings.BASE_DIR) / 'public_experience' / 'catalog.json'
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [row for row in data if row.get('active') is True and row.get('web_approved') is True]


@require_GET
def bootstrap(request):
    return JsonResponse({'schemaVersion': 1, 'maxPhotos': 6, 'localPhotosOnly': True,
                         'categories': ['旅行', '城市', '日常'], 'cloudSaveEnabled': False})


@require_GET
def templates(request):
    rows = catalogue()
    query = request.GET.get('q', '')[:80].strip().casefold()
    if query:
        rows = [r for r in rows if query in r['title'].casefold()]
    return JsonResponse({'items': [{k: r[k] for k in ('id', 'title', 'category', 'releaseId') if k in r}
                                   for r in rows[:48]], 'total': len(rows), 'page': 1, 'page_size': 48})
