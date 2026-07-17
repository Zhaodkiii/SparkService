from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView

from common.permissions import AdminCodePermission, AdminOnlyPermission
from common.response import error_response, success_response
from notification_center.models import ChannelDelivery, NotificationBusinessScene, NotificationCampaign, NotificationIntent, NotificationMessage, NotificationSuppression, NotificationTemplate, ProviderEvent
from notification_center.serializers import (
    AdminNotificationUserListQuerySerializer,
    NotificationBusinessSceneSerializer,
    NotificationCampaignSerializer,
    NotificationIntentSerializer,
    NotificationMessageSerializer,
    NotificationSuppressionSerializer,
    NotificationTemplateSerializer,
)
from notification_center.services import NotificationCenterService

User = get_user_model()


class AdminNotificationUserListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        serializer = AdminNotificationUserListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = NotificationCenterService.list_notification_users(**serializer.validated_data)
        return success_response(result, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationOverviewView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        window_days = int(request.query_params.get("window_days") or 7)
        payload = NotificationCenterService.get_overview(window_days=window_days)
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationSceneListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = NotificationBusinessScene.objects.select_related("topic").order_by("domain", "business_type", "event_name")
        q = (request.query_params.get("q") or "").strip()
        if q:
            queryset = queryset.filter(Q(key__icontains=q) | Q(display_name__icontains=q) | Q(description__icontains=q))
        for param, field in (
            ("domain", "domain"),
            ("business_type", "business_type"),
            ("category", "category"),
            ("status", "status"),
            ("owner_team", "owner_team"),
        ):
            value = (request.query_params.get(param) or "").strip()
            if value:
                queryset = queryset.filter(**{field: value})
        channel = (request.query_params.get("channel") or "").strip()
        if channel:
            queryset = queryset.filter(default_routing__icontains=channel)
        missing_template = (request.query_params.get("missing_template") or "").strip().lower()
        if missing_template in {"1", "true", "yes"}:
            queryset = queryset.filter(default_template_key="")
        page = int(request.query_params.get("page") or 1)
        page_size = int(request.query_params.get("page_size") or 50)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": NotificationBusinessSceneSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationSceneDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, scene_key: str):
        row = get_object_or_404(NotificationBusinessScene.objects.select_related("topic"), key=scene_key)
        return success_response(NotificationBusinessSceneSerializer(row).data, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationIntentListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = (
            NotificationIntent.objects.annotate(
                recipient_count=Count("recipient_messages", distinct=True),
                message_count=Count("messages", distinct=True),
                delivery_count=Count("messages__channel_deliveries", distinct=True),
            )
            .order_by("-created_at", "-id")
        )
        for param in ("business_scene", "business_domain", "business_type", "business_id", "business_reference_type", "trace_id", "status", "event_id"):
            value = (request.query_params.get(param) or "").strip()
            if value:
                queryset = queryset.filter(**{param: value})
        q = (request.query_params.get("q") or "").strip()
        if q:
            queryset = queryset.filter(
                Q(business_scene__icontains=q)
                | Q(business_id__icontains=q)
                | Q(idempotency_key__icontains=q)
                | Q(event_id__icontains=q)
                | Q(trace_id__icontains=q)
            )
        page = int(request.query_params.get("page") or 1)
        page_size = int(request.query_params.get("page_size") or 20)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": NotificationIntentSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationIntentDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, intent_id: int):
        row = get_object_or_404(
            NotificationIntent.objects.annotate(
                recipient_count=Count("recipient_messages", distinct=True),
                message_count=Count("messages", distinct=True),
                delivery_count=Count("messages__channel_deliveries", distinct=True),
            ),
            pk=intent_id,
        )
        messages = NotificationMessage.objects.select_related("user", "campaign", "intent").filter(intent_id=row.id).order_by("created_at", "id")
        data = NotificationIntentSerializer(row).data
        data["messages"] = NotificationMessageSerializer(messages, many=True).data
        return success_response(data, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationSendView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:notification:send"

    def post(self, request):
        campaign = NotificationCenterService.create_campaign_and_enqueue(
            campaign_name=request.data.get("campaign_name") or "",
            channels=request.data.get("channels") or [],
            title=request.data.get("title") or "",
            body=request.data.get("body") or "",
            payload=request.data.get("payload") or {},
            user_id=request.data.get("user_id"),
            user_ids=request.data.get("user_ids") or [],
            filters=request.data.get("filters") or {},
            template_id=request.data.get("template_id"),
            schedule_at=request.data.get("schedule_at"),
            created_by_id=getattr(request.user, "id", None),
            request_id=(request.headers.get("X-Request-ID") or "").strip(),
        )
        payload = NotificationCampaignSerializer(campaign).data
        return success_response(payload, msg="queued", code=0, status_code=status.HTTP_201_CREATED)


class AdminNotificationTemplateListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        payload = NotificationTemplateSerializer(NotificationCenterService.list_templates(), many=True).data
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        serializer = NotificationTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        NotificationCenterService.publish_template_snapshot(template=row, created_by_id=getattr(request.user, "id", None))
        return success_response(NotificationTemplateSerializer(row).data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminNotificationTemplateDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def patch(self, request, template_id: int):
        row = get_object_or_404(NotificationTemplate, pk=template_id)
        serializer = NotificationTemplateSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        NotificationCenterService.publish_template_snapshot(template=row, created_by_id=getattr(request.user, "id", None))
        return success_response(NotificationTemplateSerializer(row).data, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def delete(self, request, template_id: int):
        row = get_object_or_404(NotificationTemplate, pk=template_id)
        row.is_active = False
        row.save(update_fields=["is_active", "updated_at"])
        return success_response({}, msg="deleted", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationPreviewView(APIView):
    permission_classes = [AdminOnlyPermission]

    def post(self, request):
        user = request.user
        user_id = request.data.get("user_id")
        if user_id:
            user = get_object_or_404(User, pk=user_id)

        template = None
        template_id = request.data.get("template_id")
        if template_id:
            template = get_object_or_404(NotificationTemplate, pk=template_id)

        title, body, payload = NotificationCenterService.build_message_content(
            user=user,
            template=template,
            title=request.data.get("title") or "",
            body=request.data.get("body") or "",
            payload=request.data.get("payload") or {},
        )
        result = {
            "title": title,
            "body": body,
            "payload": payload,
            "context": NotificationCenterService.build_context_for_user(user),
        }
        return success_response(result, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationCampaignListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = NotificationCampaign.objects.select_related("created_by", "template").order_by("-created_at", "-id")
        q = (request.query_params.get("q") or "").strip()
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(title__icontains=q) | Q(request_id__icontains=q))
        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        page = int(request.query_params.get("page") or 1)
        page_size = int(request.query_params.get("page_size") or 20)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": NotificationCampaignSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationRecordListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, channel: str):
        if channel not in {
            "all",
            NotificationMessage.Channel.APNS,
            NotificationMessage.Channel.EMAIL,
            NotificationMessage.Channel.SMS,
            NotificationMessage.Channel.IN_APP,
        }:
            return error_response(msg="invalid_channel", code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        queryset = NotificationMessage.objects.select_related("user", "campaign", "intent").order_by("-created_at", "-id")
        if channel != "all":
            queryset = queryset.filter(channel=channel)
        q = (request.query_params.get("q") or "").strip()
        if q:
            search_q = (
                Q(user__username__icontains=q)
                | Q(user__email__icontains=q)
                | Q(title__icontains=q)
                | Q(receiver_phone__icontains=q)
                | Q(receiver_email__icontains=q)
                | Q(provider_message_id__icontains=q)
                | Q(provider_request_id__icontains=q)
            )
            if "@" in q:
                search_q |= Q(channel_deliveries__endpoint_hmac=NotificationCenterService._email_hmac(q))
            elif any(ch.isdigit() for ch in q):
                normalized_phone = NotificationCenterService._normalize_phone(q)
                if normalized_phone:
                    search_q |= Q(channel_deliveries__endpoint_hmac=NotificationCenterService._phone_hmac(normalized_phone))
            queryset = queryset.filter(search_q).distinct()
        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        page = int(request.query_params.get("page") or 1)
        page_size = int(request.query_params.get("page_size") or 20)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": NotificationMessageSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationLogListView(AdminNotificationRecordListView):
    pass


class AdminNotificationLogDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, log_id: int):
        row = get_object_or_404(NotificationMessage.objects.select_related("user", "campaign", "intent"), pk=log_id)
        return success_response(NotificationMessageSerializer(row).data, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminSmsSendDetailsQueryView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:notification:sms:query_send_details"

    def post(self, request, message_id: int):
        try:
            row = NotificationCenterService.query_sms_send_details_for_message(
                message_id=message_id,
                request_id=getattr(request, "request_id", "") or "",
                operator_user_id=getattr(request.user, "id", None),
            )
        except NotificationMessage.DoesNotExist:
            return error_response(msg="sms_message_not_found", code=40401, status_code=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return error_response(msg=str(exc), code=40001, status_code=status.HTTP_400_BAD_REQUEST)
        return success_response(NotificationMessageSerializer(row).data, msg="queried", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationSuppressionListCreateView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = NotificationSuppression.objects.select_related("user", "created_by").order_by("-created_at", "-id")
        q = (request.query_params.get("q") or "").strip()
        if q:
            queryset = queryset.filter(
                Q(user__username__icontains=q)
                | Q(user__email__icontains=q)
                | Q(endpoint_hmac__icontains=q)
                | Q(detail__icontains=q)
            )
        channel = (request.query_params.get("channel") or "").strip()
        if channel:
            queryset = queryset.filter(channel=channel)
        reason = (request.query_params.get("reason") or "").strip()
        if reason:
            queryset = queryset.filter(reason=reason)
        only_active = str(request.query_params.get("only_active") or "true").lower() in {"1", "true", "yes", "y"}
        if only_active:
            now = timezone.now()
            queryset = queryset.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))

        page = int(request.query_params.get("page") or 1)
        page_size = int(request.query_params.get("page_size") or 20)
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        payload = {
            "items": NotificationSuppressionSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def post(self, request):
        serializer = NotificationSuppressionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = serializer.save(created_by=request.user if request.user.is_authenticated else None)
        return success_response(NotificationSuppressionSerializer(row).data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class AdminNotificationSuppressionReleaseView(APIView):
    permission_classes = [AdminOnlyPermission]

    def post(self, request, suppression_id: int):
        row = get_object_or_404(NotificationSuppression, pk=suppression_id)
        row.expires_at = timezone.now()
        row.save(update_fields=["expires_at", "updated_at"])
        return success_response(NotificationSuppressionSerializer(row).data, msg="released", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationAnalyticsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        window_days = max(1, min(int(request.query_params.get("window_days") or 7), 90))
        since = timezone.now() - timedelta(days=window_days)
        messages = NotificationMessage.objects.filter(created_at__gte=since)
        deliveries = ChannelDelivery.objects.filter(created_at__gte=since)
        provider_events = ProviderEvent.objects.filter(created_at__gte=since)
        suppressions = NotificationSuppression.objects.filter(created_at__gte=since)

        def count_rows(queryset, field: str) -> list[dict]:
            return list(queryset.values(field).annotate(count=Count("id")).order_by(field))

        channel_stats = []
        for channel in [NotificationMessage.Channel.APNS, NotificationMessage.Channel.EMAIL, NotificationMessage.Channel.SMS]:
            channel_messages = messages.filter(channel=channel)
            channel_deliveries = deliveries.filter(channel=channel)
            message_total = channel_messages.count()
            delivered = channel_deliveries.filter(status=ChannelDelivery.Status.DELIVERED).count()
            failed = channel_deliveries.filter(
                status__in=[ChannelDelivery.Status.DELIVERY_FAILED, ChannelDelivery.Status.SUBMIT_FAILED, ChannelDelivery.Status.EXPIRED]
            ).count()
            channel_stats.append(
                {
                    "channel": channel,
                    "message_total": message_total,
                    "delivery_total": channel_deliveries.count(),
                    "delivered": delivered,
                    "failed": failed,
                    "success_rate": round((delivered / message_total) * 100, 2) if message_total else 0,
                    "failure_rate": round((failed / message_total) * 100, 2) if message_total else 0,
                }
            )

        payload = {
            "window_days": window_days,
            "since": since,
            "summary": {
                "messages": messages.count(),
                "deliveries": deliveries.count(),
                "provider_events": provider_events.count(),
                "suppressions": suppressions.count(),
            },
            "channel_stats": channel_stats,
            "message_status_stats": count_rows(messages, "status"),
            "delivery_status_stats": count_rows(deliveries, "status"),
            "provider_event_stats": count_rows(provider_events, "normalized_type"),
            "suppression_reason_stats": count_rows(suppressions, "reason"),
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class AdminNotificationChannelSettingsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        payload = {
            "channels": [
                {
                    "channel": "apns",
                    "name": "APNs",
                    "enabled": bool(getattr(settings, "APNS_TOPIC", "") and getattr(settings, "APNS_KEY_ID", "") and getattr(settings, "APNS_TEAM_ID", "")),
                    "environment": "sandbox" if bool(getattr(settings, "APNS_USE_SANDBOX", True)) else "production",
                    "config": {
                        "topic": getattr(settings, "APNS_TOPIC", "") or "",
                        "key_id_configured": bool(getattr(settings, "APNS_KEY_ID", "")),
                        "team_id_configured": bool(getattr(settings, "APNS_TEAM_ID", "")),
                        "auth_key_path_configured": bool(getattr(settings, "APNS_AUTH_KEY_PATH", "")),
                    },
                },
                {
                    "channel": "sms",
                    "name": "阿里云短信",
                    "enabled": bool(
                        getattr(settings, "ALIYUN_SMS_ACCESS_KEY_ID", "")
                        and getattr(settings, "ALIYUN_SMS_ACCESS_KEY_SECRET", "")
                        and getattr(settings, "ALIYUN_SMS_SIGN_NAME", "")
                        and (getattr(settings, "ALIYUN_SMS_NOTIFICATION_TEMPLATE_CODE", "") or getattr(settings, "ALIYUN_SMS_OTP_TEMPLATE_CODE", ""))
                    ),
                    "environment": "aliyun",
                    "config": {
                        "endpoint": getattr(settings, "ALIYUN_SMS_ENDPOINT", "") or "dysmsapi.aliyuncs.com",
                        "sign_name": getattr(settings, "ALIYUN_SMS_SIGN_NAME", "") or "",
                        "access_key_configured": bool(getattr(settings, "ALIYUN_SMS_ACCESS_KEY_ID", "") and getattr(settings, "ALIYUN_SMS_ACCESS_KEY_SECRET", "")),
                        "notification_template_configured": bool(getattr(settings, "ALIYUN_SMS_NOTIFICATION_TEMPLATE_CODE", "")),
                        "otp_template_configured": bool(getattr(settings, "ALIYUN_SMS_OTP_TEMPLATE_CODE", "")),
                    },
                },
                {
                    "channel": "email",
                    "name": "邮箱",
                    "enabled": bool(getattr(settings, "EMAIL_BACKEND", "")),
                    "environment": getattr(settings, "EMAIL_BACKEND", ""),
                    "config": {
                        "host": getattr(settings, "EMAIL_HOST", "") or "",
                        "port": getattr(settings, "EMAIL_PORT", None),
                        "default_from_email": getattr(settings, "DEFAULT_FROM_EMAIL", "") or "",
                        "host_user_configured": bool(getattr(settings, "EMAIL_HOST_USER", "")),
                        "host_password_configured": bool(getattr(settings, "EMAIL_HOST_PASSWORD", "")),
                        "use_ssl": bool(getattr(settings, "EMAIL_USE_SSL", False)),
                        "use_tls": bool(getattr(settings, "EMAIL_USE_TLS", False)),
                        "timeout": getattr(settings, "EMAIL_TIMEOUT", None),
                    },
                },
            ]
        }
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
