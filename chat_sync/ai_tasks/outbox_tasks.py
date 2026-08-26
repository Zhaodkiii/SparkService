from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from asgiref.sync import async_to_sync
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from channels.layers import get_channel_layer

from chat_sync.ai_models import ChatEventOutbox

logger = logging.getLogger("chat_sync.ai.outbox")


@shared_task(name="chat_sync.ai_tasks.outbox_tasks.relay_chat_event_outbox")
def relay_chat_event_outbox(limit: int = 100):
    delivered = 0
    now = timezone.now()
    stale_before = now - timedelta(minutes=2)
    ChatEventOutbox.objects.filter(
        status=ChatEventOutbox.Status.PROCESSING,
        locked_at__lt=stale_before,
    ).update(
        status=ChatEventOutbox.Status.FAILED,
        lock_owner="",
        locked_at=None,
        available_at=now,
        last_error="stale relay lock recovered",
    )
    for _ in range(limit):
        owner = uuid.uuid4().hex
        with transaction.atomic():
            item = (
                ChatEventOutbox.objects.select_for_update(skip_locked=True)
                .filter(status__in=[ChatEventOutbox.Status.PENDING, ChatEventOutbox.Status.FAILED])
                .filter(Q(available_at__isnull=True) | Q(available_at__lte=timezone.now()))
                .order_by("id")
                .first()
            )
            if item is None:
                break
            item.status = ChatEventOutbox.Status.PROCESSING
            item.lock_owner = owner
            item.locked_at = timezone.now()
            item.attempts += 1
            item.save(update_fields=["status", "lock_owner", "locked_at", "attempts", "updated_at"])
        try:
            async_to_sync(get_channel_layer().group_send)(item.channel_group, {"type": "chat.run.event", "event": item.payload})
            published_at = timezone.now()
            ChatEventOutbox.objects.filter(pk=item.pk, lock_owner=owner).update(status=ChatEventOutbox.Status.PUBLISHED, published_at=published_at, lock_owner="", locked_at=None)
            delivered += 1
            # W0 observability: commit-to-publish latency, no new metrics infra required.
            publish_elapsed_ms = int((published_at - item.created_at).total_seconds() * 1000)
            logger.info(
                "chat_event_outbox.relayed id=%s channel_group=%s attempts=%s publish_elapsed_ms=%s",
                item.pk,
                item.channel_group,
                item.attempts,
                publish_elapsed_ms,
            )
        except Exception as exc:  # pragma: no cover - broker integration
            logger.exception("chat_event_outbox.relay_failed id=%s", item.pk)
            delay_seconds = min(60, 2 ** min(item.attempts, 6))
            ChatEventOutbox.objects.filter(pk=item.pk, lock_owner=owner).update(
                status=ChatEventOutbox.Status.FAILED,
                last_error=str(exc)[:2000],
                available_at=timezone.now() + timedelta(seconds=delay_seconds),
                lock_owner="",
                locked_at=None,
            )
    return {"delivered": delivered}
