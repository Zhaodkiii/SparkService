"""One durable FIFO queue and one claim/report endpoint for all diary ZIPs."""
import uuid
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ResourceTask, Upload
from .views import ProcessorPermission, Conflict, Processor as PublicProcessor
from diary_customizations.processor import Processor as PrivateProcessor
from diary_customizations.models import Job, Request
from diary_customizations.storage import scope


def enqueue(source):
    field = 'upload' if isinstance(source, Upload) else 'delivery_job'
    if field == 'delivery_job' and source.kind != 'delivery':
        raise ValueError('Photos must never enter the resource queue')
    task, created = ResourceTask.objects.get_or_create(
        **{field: source})
    if not created:
        task.status = 'queued'
        task.lease = task.lease_until = None
        task.created_at = timezone.now()
        task.save()
    return task


def eligible():
    return (Q(upload__status__in=['queued', 'processing']) |
            Q(delivery_job__kind='delivery', delivery_job__status__in=['queued', 'processing'],
              delivery_job__request__deleted_at__isnull=True) &
            ~Q(delivery_job__request__status__in=['cancelled', 'rejected']))


class Processor(APIView):
    authentication_classes = []
    permission_classes = [ProcessorPermission]

    @transaction.atomic
    def post(self, request):
        now = timezone.now()
        if request.data.get('action') == 'claim':
            while True:
                task = ResourceTask.objects.select_for_update(of=('self',)).filter(eligible()).filter(
                    Q(status='queued') | Q(status='processing', lease_until__lt=now)
                ).order_by('created_at', 'id').first()
                if not task:
                    return Response(status=204)
                # Lock source then re-check in case a cancellation/accept operation won the race.
                private = bool(task.delivery_job_id)
                source = (Job if private else Upload).objects.select_for_update().get(
                    pk=task.delivery_job_id if private else task.upload_id)
                obj = Request.objects.select_for_update().get(pk=source.request_id) if private else None
                if source.status not in ('queued', 'processing') or (private and (
                        source.kind != 'delivery' or obj.deleted_at or obj.status in ('cancelled', 'rejected') or
                        obj.accepted_submission_id != source.submission_id)):
                    task.status = 'abandoned'
                    task.save()
                    continue
                task.status = source.status = 'processing'
                task.lease = source.lease = uuid.uuid4()
                task.lease_until = source.lease_until = now + timedelta(minutes=30)
                task.save()
                source.save()
                data = dict(id=str(task.pk), source_id=str(source.pk), lease=str(task.lease),
                            resource_type='customization' if private else 'public',
                            object_key=source.object_key, size=source.size)
                if private:
                    data.update(request_id=str(obj.pk), kind='delivery', sha256=source.sha256, scope=scope(obj))
                else:
                    data.update(mode=source.mode)
                return Response(data)
        task = get_object_or_404(ResourceTask.objects.select_for_update(of=('self',)), pk=request.data.get('id'))
        if str(task.lease) != request.data.get('lease'):
            raise Conflict('处理租约已变化')
        if task.status == 'done':
            return Response({'status': 'done'})
        if task.status != 'processing' or not task.lease_until or task.lease_until < now:
            raise Conflict('处理租约已过期')
        # Keep the same request; only map its queue ID to the domain record ID.
        mapped = dict(request.data)
        mapped['id'] = str(task.delivery_job_id or task.upload_id)
        from types import SimpleNamespace
        response = (PrivateProcessor() if task.delivery_job_id else PublicProcessor()).post(SimpleNamespace(data=mapped))
        task.status = 'done'
        task.save(update_fields=['status'])
        return response
