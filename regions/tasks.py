import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from .sync import synchronize
from .models import RegionState

@shared_task
def check_regions(force=False):
    if settings.REGIONS_SYNC_ENABLED or force: synchronize(force=force)
    state=RegionState.objects.filter(pk=1).first()
    if not state or not state.last_checked_at or (timezone.now()-state.last_checked_at).days>=90:
        logging.getLogger(__name__).warning('Region dataset has not been verified within 90 days')
