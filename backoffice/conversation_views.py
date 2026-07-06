from __future__ import annotations

from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import BooleanField, Case, Count, Exists, IntegerField, Max, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.views import APIView

from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from common.permissions import SuperAdminOnlyPermission
from common.response import success_response

from backoffice.audit import write_audit_log
from backoffice.conversation_serializers import (
    HEAVY_BLOCK_KINDS,
    MEDICAL_BLOCK_KINDS,
    block_kind_filter_values,
    format_user_display_name,
    format_user_status,
    is_anonymized_user,
    recent_days_trend,
    serialize_block,
    serialize_conversation_user,
    serialize_message,
    serialize_message_debug,
    serialize_thread,
)

User = get_user_model()


def _paginate(queryset, request, default_page_size: int = 20):
    page = max(int(request.query_params.get("page", "1")), 1)
    page_size = min(max(int(request.query_params.get("page_size", str(default_page_size))), 1), 100)
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)
    return page_obj, page_size, paginator


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


class AdminConversationUserListView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request):
        latest_message = ChatMessage.objects.filter(user_id=OuterRef("pk")).order_by("-created_at", "-id")
        user_messages = ChatMessage.objects.filter(user_id=OuterRef("pk"))
        user_threads = ChatThread.objects.filter(user_id=OuterRef("pk"))

        message_count_sq = user_messages.order_by().values("user_id").annotate(count=Count("id")).values("count")[:1]
        user_message_count_sq = (
            user_messages.filter(role=ChatMessage.Role.USER)
            .order_by()
            .values("user_id")
            .annotate(count=Count("id"))
            .values("count")[:1]
        )
        thread_count_sq = user_threads.order_by().values("user_id").annotate(count=Count("id")).values("count")[:1]

        queryset = (
            User.objects.filter(Exists(user_messages))
            .annotate(
                last_conversation_at=Subquery(latest_message.values("created_at")[:1]),
            )
        )

        user_id = (request.query_params.get("user_id") or "").strip()
        if user_id.isdigit():
            queryset = queryset.filter(id=int(user_id))

        keyword = (request.query_params.get("keyword") or request.query_params.get("q") or "").strip()
        if keyword:
            queryset = queryset.filter(Q(username__icontains=keyword) | Q(email__icontains=keyword))

        started_at = _parse_dt(request.query_params.get("started_at"))
        ended_at = _parse_dt(request.query_params.get("ended_at"))
        if started_at:
            queryset = queryset.filter(last_conversation_at__gte=started_at)
        if ended_at:
            queryset = queryset.filter(last_conversation_at__lte=ended_at)

        model_name = (request.query_params.get("model_name") or "").strip()
        if model_name:
            queryset = queryset.filter(
                Exists(
                    user_messages.filter(
                        role=ChatMessage.Role.ASSISTANT,
                        model_name__icontains=model_name,
                    )
                )
            )

        is_active = request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        has_user_message = request.query_params.get("has_user_message")
        if has_user_message == "true":
            queryset = queryset.filter(Exists(user_messages.filter(role=ChatMessage.Role.USER)))
        elif has_user_message == "false":
            queryset = queryset.filter(~Exists(user_messages.filter(role=ChatMessage.Role.USER)))

        min_message_count = request.query_params.get("min_message_count")
        max_message_count = request.query_params.get("max_message_count")
        needs_message_count = (
            (min_message_count and min_message_count.isdigit())
            or (max_message_count and max_message_count.isdigit())
            or (request.query_params.get("ordering") or "").strip() in {"message_count", "-message_count"}
        )
        if needs_message_count:
            queryset = queryset.annotate(
                message_count=Coalesce(
                    Subquery(message_count_sq, output_field=IntegerField()),
                    Value(0),
                )
            )
        if min_message_count and min_message_count.isdigit():
            queryset = queryset.filter(message_count__gte=int(min_message_count))
        if max_message_count and max_message_count.isdigit():
            queryset = queryset.filter(message_count__lte=int(max_message_count))

        min_thread_count = request.query_params.get("min_thread_count")
        max_thread_count = request.query_params.get("max_thread_count")
        needs_thread_count = (
            (min_thread_count and min_thread_count.isdigit())
            or (max_thread_count and max_thread_count.isdigit())
            or (request.query_params.get("ordering") or "").strip() in {"thread_count", "-thread_count"}
        )
        if needs_thread_count:
            queryset = queryset.annotate(
                thread_count=Coalesce(
                    Subquery(thread_count_sq, output_field=IntegerField()),
                    Value(0),
                )
            )
        if min_thread_count and min_thread_count.isdigit():
            queryset = queryset.filter(thread_count__gte=int(min_thread_count))
        if max_thread_count and max_thread_count.isdigit():
            queryset = queryset.filter(thread_count__lte=int(max_thread_count))

        ordering = (request.query_params.get("ordering") or "-last_conversation_at").strip()
        allowed = {
            "last_conversation_at",
            "-last_conversation_at",
            "thread_count",
            "-thread_count",
            "message_count",
            "-message_count",
            "user_message_count",
            "-user_message_count",
            "date_joined",
            "-date_joined",
            "id",
            "-id",
        }
        if ordering not in allowed:
            ordering = "-last_conversation_at"
        if ordering in {"user_message_count", "-user_message_count"}:
            queryset = queryset.annotate(
                user_message_count=Coalesce(
                    Subquery(user_message_count_sq, output_field=IntegerField()),
                    Value(0),
                )
            )
        queryset = queryset.order_by(ordering, "-id")

        page_obj, page_size, paginator = _paginate(queryset, request)
        page_users = list(page_obj.object_list)
        page_user_ids = [user.id for user in page_users]

        message_stats_by_user = {
            row["user_id"]: row
            for row in ChatMessage.objects.filter(user_id__in=page_user_ids)
            .values("user_id")
            .annotate(
                message_count=Count("id"),
                tombstone_count=Count("id", filter=Q(tombstone=True)),
                user_message_count=Count("id", filter=Q(role=ChatMessage.Role.USER)),
                assistant_message_count=Count("id", filter=Q(role=ChatMessage.Role.ASSISTANT)),
                last_conversation_at=Max("created_at"),
            )
        }
        thread_stats_by_user = {
            row["user_id"]: row
            for row in ChatThread.objects.filter(user_id__in=page_user_ids)
            .values("user_id")
            .annotate(
                thread_count=Count("id"),
                active_thread_count=Count("id", filter=Q(is_deleted=False)),
                deleted_thread_count=Count("id", filter=Q(is_deleted=True)),
            )
        }
        latest_assistant_by_user = {}
        for message in (
            ChatMessage.objects.filter(user_id__in=page_user_ids, role=ChatMessage.Role.ASSISTANT)
            .select_related("thread")
            .order_by("user_id", "-created_at", "-id")
        ):
            latest_assistant_by_user.setdefault(message.user_id, message)

        page_message_stats = ChatMessage.objects.filter(user_id__in=page_user_ids).aggregate(
            message_count=Count("id"),
            user_message_count=Count("id", filter=Q(role=ChatMessage.Role.USER)),
            assistant_message_count=Count("id", filter=Q(role=ChatMessage.Role.ASSISTANT)),
        )
        page_thread_stats = ChatThread.objects.filter(user_id__in=page_user_ids).aggregate(
            thread_count=Count("id"),
            deleted_thread_count=Count("id", filter=Q(is_deleted=True)),
        )
        rows = []
        for user in page_users:
            user_message_stats = message_stats_by_user.get(user.id, {})
            user_thread_stats = thread_stats_by_user.get(user.id, {})
            latest_assistant_message = latest_assistant_by_user.get(user.id)
            last_conversation_at = user_message_stats.get("last_conversation_at")
            rows.append(
                serialize_conversation_user(
                    user,
                    annotations={
                        "thread_count": user_thread_stats.get("thread_count") or 0,
                        "active_thread_count": user_thread_stats.get("active_thread_count") or 0,
                        "deleted_thread_count": user_thread_stats.get("deleted_thread_count") or 0,
                        "message_count": user_message_stats.get("message_count") or 0,
                        "tombstone_count": user_message_stats.get("tombstone_count") or 0,
                        "user_message_count": user_message_stats.get("user_message_count") or 0,
                        "assistant_message_count": user_message_stats.get("assistant_message_count") or 0,
                        "last_conversation_at": last_conversation_at.isoformat() if last_conversation_at else None,
                        "last_thread_id": latest_assistant_message.thread_id if latest_assistant_message else None,
                        "last_thread_title": latest_assistant_message.thread.title if latest_assistant_message else "",
                        "last_model_name": latest_assistant_message.model_name if latest_assistant_message else "",
                    },
                )
            )

        write_audit_log(
            request,
            action="admin.conversation.users.list",
            resource_type="conversation_user",
            resource_id="list",
            status_code=200,
        )

        payload = {
            "items": rows,
            "stats": {
                "user_count": paginator.count,
                "thread_count": page_thread_stats.get("thread_count") or 0,
                "message_count": page_message_stats.get("message_count") or 0,
                "user_message_count": page_message_stats.get("user_message_count") or 0,
                "assistant_message_count": page_message_stats.get("assistant_message_count") or 0,
                "deleted_thread_count": page_thread_stats.get("deleted_thread_count") or 0,
            },
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminConversationUserSummaryView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request, user_id: int):
        user = get_object_or_404(User, pk=user_id)
        if not ChatMessage.objects.filter(user_id=user.id).exists():
            return success_response(
                {"detail": "user_has_no_conversations"},
                msg="not_found",
                code=40401,
                status_code=status.HTTP_404_NOT_FOUND,
            )

        thread_stats = ChatThread.objects.filter(user_id=user.id).aggregate(
            thread_count=Count("id"),
            deleted_thread_count=Count("id", filter=Q(is_deleted=True)),
        )
        message_stats = ChatMessage.objects.filter(user_id=user.id).aggregate(
            message_count=Count("id"),
            tombstone_count=Count("id", filter=Q(tombstone=True)),
            user_message_count=Count("id", filter=Q(role=ChatMessage.Role.USER)),
            assistant_message_count=Count("id", filter=Q(role=ChatMessage.Role.ASSISTANT)),
            last_conversation_at=Max("created_at"),
        )
        block_stats = ChatMessageBlock.objects.filter(user_id=user.id).aggregate(
            medical_block_count=Count("id", filter=Q(kind__in=block_kind_filter_values(MEDICAL_BLOCK_KINDS))),
            heavy_block_count=Count(
                "id",
                filter=Q(
                    kind__in=block_kind_filter_values(
                        HEAVY_BLOCK_KINDS | {"tool", "imageGallery", "fileAttachments"}
                    )
                ),
            ),
            attachment_count=Count("id", filter=Q(kind__in=block_kind_filter_values({"imageGallery", "fileAttachments"}))),
            last_medical_resource_at=Max(
                "updated_at",
                filter=Q(kind__in=block_kind_filter_values(MEDICAL_BLOCK_KINDS)),
            ),
        )
        model_distribution = list(
            ChatMessage.objects.filter(user_id=user.id, role=ChatMessage.Role.ASSISTANT)
            .exclude(model_name="")
            .values("model_name")
            .annotate(count=Count("id"))
            .order_by("-count", "model_name")[:20]
        )

        write_audit_log(
            request,
            action="admin.conversation.user.summary",
            resource_type="conversation_user",
            resource_id=str(user.id),
            status_code=200,
        )

        payload = {
            "user": {
                "user_id": user.id,
                "username": format_user_display_name(user),
                "raw_username": user.username,
                "email": user.email or "",
                "is_active": user.is_active,
                "user_status": format_user_status(user),
                "is_anonymized": is_anonymized_user(user),
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            },
            "stats": {
                "thread_count": thread_stats.get("thread_count") or 0,
                "deleted_thread_count": thread_stats.get("deleted_thread_count") or 0,
                "message_count": message_stats.get("message_count") or 0,
                "tombstone_count": message_stats.get("tombstone_count") or 0,
                "user_message_count": message_stats.get("user_message_count") or 0,
                "assistant_message_count": message_stats.get("assistant_message_count") or 0,
                "last_conversation_at": message_stats.get("last_conversation_at").isoformat()
                if message_stats.get("last_conversation_at")
                else None,
                "medical_block_count": block_stats.get("medical_block_count") or 0,
                "heavy_block_count": block_stats.get("heavy_block_count") or 0,
                "attachment_count": block_stats.get("attachment_count") or 0,
                "last_medical_resource_at": block_stats.get("last_medical_resource_at").isoformat()
                if block_stats.get("last_medical_resource_at")
                else None,
            },
            "model_distribution": model_distribution,
            "recent_7_day_trend": recent_days_trend(user.id, days=7),
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminConversationThreadListView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request, user_id: int):
        user = get_object_or_404(User, pk=user_id)
        block_qs = ChatMessageBlock.objects.filter(thread_id=OuterRef("pk"))
        queryset = (
            ChatThread.objects.filter(user_id=user.id)
            .annotate(
                message_count=Count("messages", distinct=True),
                tombstone_count=Count("messages", filter=Q(messages__tombstone=True), distinct=True),
                user_message_count=Count(
                    "messages",
                    filter=Q(messages__role=ChatMessage.Role.USER),
                    distinct=True,
                ),
                assistant_message_count=Count(
                    "messages",
                    filter=Q(messages__role=ChatMessage.Role.ASSISTANT),
                    distinct=True,
                ),
                last_message_at=Max("messages__created_at"),
                has_tool=Exists(block_qs.filter(kind="tool")),
                has_attachment=Exists(block_qs.filter(kind__in=["imageGallery", "fileAttachments"])),
                has_failed_message=Case(
                    When(
                        Exists(
                            ChatMessage.objects.filter(
                                thread_id=OuterRef("pk"),
                                delivery_state=ChatMessage.DeliveryState.FAILED,
                            )
                        ),
                        then=Value(True),
                    ),
                    When(
                        Exists(
                            ChatMessageBlock.objects.filter(
                                thread_id=OuterRef("pk"),
                                status=ChatMessageBlock.Status.FAILED,
                            )
                        ),
                        then=Value(True),
                    ),
                    default=Value(False),
                    output_field=BooleanField(),
                ),
                medical_block_count=Count(
                    "messages__blocks",
                    filter=Q(messages__blocks__kind__in=block_kind_filter_values(MEDICAL_BLOCK_KINDS)),
                    distinct=True,
                ),
                heavy_block_count=Count(
                    "messages__blocks",
                    filter=Q(
                        messages__blocks__kind__in=block_kind_filter_values(
                            HEAVY_BLOCK_KINDS | {"tool", "imageGallery", "fileAttachments"}
                        )
                    ),
                    distinct=True,
                ),
                attachment_count=Count(
                    "messages__blocks",
                    filter=Q(
                        messages__blocks__kind__in=block_kind_filter_values({"imageGallery", "fileAttachments"})
                    ),
                    distinct=True,
                ),
                last_medical_resource_at=Max(
                    "messages__blocks__updated_at",
                    filter=Q(messages__blocks__kind__in=block_kind_filter_values(MEDICAL_BLOCK_KINDS)),
                ),
            )
            .order_by("-last_message_at", "-updated_at", "-created_at")
        )

        keyword = (request.query_params.get("keyword") or "").strip()
        if keyword:
            queryset = queryset.filter(Q(title__icontains=keyword) | Q(id__icontains=keyword))

        thread_id = (request.query_params.get("thread_id") or "").strip()
        if thread_id:
            queryset = queryset.filter(id=thread_id)

        started_at = _parse_dt(request.query_params.get("started_at"))
        ended_at = _parse_dt(request.query_params.get("ended_at"))
        if started_at:
            queryset = queryset.filter(updated_at__gte=started_at)
        if ended_at:
            queryset = queryset.filter(updated_at__lte=ended_at)

        model_name = (request.query_params.get("model_name") or "").strip()
        if model_name:
            queryset = queryset.filter(current_model_name__icontains=model_name)

        deleted_filter = (request.query_params.get("deleted_filter") or request.query_params.get("include_deleted") or "all").strip()
        if deleted_filter in {"active", "false", "0"}:
            queryset = queryset.filter(is_deleted=False)
        elif deleted_filter in {"deleted", "true", "1"}:
            queryset = queryset.filter(is_deleted=True)

        has_tool = request.query_params.get("has_tool")
        if has_tool == "true":
            queryset = queryset.filter(has_tool=True)
        elif has_tool == "false":
            queryset = queryset.filter(has_tool=False)

        has_attachment = request.query_params.get("has_attachment")
        if has_attachment == "true":
            queryset = queryset.filter(has_attachment=True)
        elif has_attachment == "false":
            queryset = queryset.filter(has_attachment=False)

        has_failed_message = request.query_params.get("has_failed_message")
        if has_failed_message == "true":
            queryset = queryset.filter(has_failed_message=True)
        elif has_failed_message == "false":
            queryset = queryset.filter(has_failed_message=False)

        page_obj, page_size, paginator = _paginate(queryset, request)
        items = []
        for thread in page_obj.object_list:
            items.append(
                serialize_thread(
                    thread,
                    annotations={
                        "message_count": thread.message_count,
                        "tombstone_count": thread.tombstone_count,
                        "user_message_count": thread.user_message_count,
                        "assistant_message_count": thread.assistant_message_count,
                        "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else None,
                        "has_tool": thread.has_tool,
                        "has_attachment": thread.has_attachment,
                        "has_failed_message": thread.has_failed_message,
                        "medical_block_count": thread.medical_block_count,
                        "heavy_block_count": thread.heavy_block_count,
                        "attachment_count": thread.attachment_count,
                        "last_medical_resource_at": thread.last_medical_resource_at.isoformat()
                        if thread.last_medical_resource_at
                        else None,
                    },
                )
            )

        write_audit_log(
            request,
            action="admin.conversation.threads.list",
            resource_type="conversation_user",
            resource_id=str(user.id),
            status_code=200,
        )

        payload = {
            "user": {
                "user_id": user.id,
                "username": format_user_display_name(user),
                "email": user.email or "",
                "user_status": format_user_status(user),
            },
            "items": items,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminConversationMessageListView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request, user_id: int, thread_id):
        user = get_object_or_404(User, pk=user_id)
        thread = get_object_or_404(ChatThread, id=thread_id, user_id=user.id)

        queryset = ChatMessage.objects.filter(user_id=user.id, thread_id=thread.id).prefetch_related("blocks")

        role = (request.query_params.get("role") or "").strip()
        if role in {ChatMessage.Role.SYSTEM, ChatMessage.Role.USER, ChatMessage.Role.ASSISTANT}:
            queryset = queryset.filter(role=role)

        include_tombstone = request.query_params.get("include_tombstone", "true").strip().lower()
        if include_tombstone in {"false", "0"}:
            queryset = queryset.filter(tombstone=False)

        block_kind = (request.query_params.get("block_kind") or "").strip()
        if block_kind:
            queryset = queryset.filter(blocks__kind=block_kind).distinct()

        include_raw = request.query_params.get("include_raw", "false").strip().lower() in {"true", "1"}

        before = request.query_params.get("before")
        after = request.query_params.get("after")
        if before and str(before).isdigit():
            pivot = ChatMessage.objects.filter(id=int(before), thread_id=thread.id).first()
            if pivot:
                queryset = queryset.filter(
                    Q(created_at__lt=pivot.created_at)
                    | Q(created_at=pivot.created_at, id__lt=pivot.id)
                )
        if after and str(after).isdigit():
            pivot = ChatMessage.objects.filter(id=int(after), thread_id=thread.id).first()
            if pivot:
                queryset = queryset.filter(
                    Q(created_at__gt=pivot.created_at)
                    | Q(created_at=pivot.created_at, id__gt=pivot.id)
                )

        queryset = queryset.order_by("created_at", "id")

        page_obj, page_size, paginator = _paginate(queryset, request, default_page_size=50)
        items = [
            serialize_message(message, include_raw=include_raw, detail_mode="list")
            for message in page_obj.object_list
        ]

        write_audit_log(
            request,
            action="admin.conversation.messages.list",
            resource_type="conversation_thread",
            resource_id=str(thread.id),
            status_code=200,
        )

        last_message = thread.messages.order_by("-created_at", "-id").first()
        last_message_at = last_message.created_at.isoformat() if last_message and last_message.created_at else None
        thread_block_stats = ChatMessageBlock.objects.filter(thread_id=thread.id).aggregate(
            medical_block_count=Count("id", filter=Q(kind__in=block_kind_filter_values(MEDICAL_BLOCK_KINDS))),
            heavy_block_count=Count(
                "id",
                filter=Q(
                    kind__in=block_kind_filter_values(
                        HEAVY_BLOCK_KINDS | {"tool", "imageGallery", "fileAttachments"}
                    )
                ),
            ),
            attachment_count=Count("id", filter=Q(kind__in=block_kind_filter_values({"imageGallery", "fileAttachments"}))),
            last_medical_resource_at=Max(
                "updated_at",
                filter=Q(kind__in=block_kind_filter_values(MEDICAL_BLOCK_KINDS)),
            ),
        )

        payload = {
            "thread": serialize_thread(
                thread,
                annotations={
                    "message_count": thread.messages.count(),
                    "tombstone_count": thread.messages.filter(tombstone=True).count(),
                    "user_message_count": thread.messages.filter(role=ChatMessage.Role.USER).count(),
                    "assistant_message_count": thread.messages.filter(role=ChatMessage.Role.ASSISTANT).count(),
                    "last_message_at": last_message_at,
                    "medical_block_count": thread_block_stats.get("medical_block_count") or 0,
                    "heavy_block_count": thread_block_stats.get("heavy_block_count") or 0,
                    "attachment_count": thread_block_stats.get("attachment_count") or 0,
                    "last_medical_resource_at": thread_block_stats.get("last_medical_resource_at").isoformat()
                    if thread_block_stats.get("last_medical_resource_at")
                    else None,
                },
            ),
            "items": items,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminConversationBlockDetailView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request, user_id: int, thread_id, block_id):
        user = get_object_or_404(User, pk=user_id)
        thread = get_object_or_404(ChatThread, id=thread_id, user_id=user.id)
        block = get_object_or_404(
            ChatMessageBlock.objects.select_related("message"),
            id=block_id,
            thread_id=thread.id,
            user_id=user.id,
        )

        write_audit_log(
            request,
            action="admin.conversation.block.detail",
            resource_type="conversation_block",
            resource_id=str(block.id),
            status_code=200,
        )

        payload = serialize_block(
            block,
            user_id=user.id,
            thread_id=thread.id,
            detail_mode="detail",
        )
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminConversationMessageDebugView(APIView):
    permission_classes = [SuperAdminOnlyPermission]

    def get(self, request, user_id: int, thread_id, message_db_id: int):
        user = get_object_or_404(User, pk=user_id)
        thread = get_object_or_404(ChatThread, id=thread_id, user_id=user.id)
        message = get_object_or_404(
            ChatMessage.objects.prefetch_related("blocks"),
            id=message_db_id,
            thread_id=thread.id,
            user_id=user.id,
        )

        write_audit_log(
            request,
            action="admin.conversation.message.debug",
            resource_type="conversation_message",
            resource_id=str(message.id),
            status_code=200,
        )

        payload = serialize_message_debug(message)
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
