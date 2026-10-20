from django.db.models import Q
from django.http import Http404
from .models import Version

def visible_version(user, pk, number):
    version = Version.objects.select_related('template__series').defer('snapshot').filter(template_id=pk, number=number).first()
    authorize(user, version)
    return version

def authorize(user, version):
    if not version or not version.template.active:
        raise Http404()
    t = version.template
    if t.audience == 'public':
        if not t.series.active: raise Http404()
    else:
        from diary_customizations.models import Delivery
        if t.owner_id != user.pk or not Delivery.objects.filter(version=version, status='delivered',
            request__owner=user, request__deleted_at__isnull=True).exists():
            raise Http404()
