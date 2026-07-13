from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.infrastructure.sms_provider import AliyunSMSProvider, SMSDeliveryQueryResult, SMSProviderResult
from notification_center.models import (
    AudienceSnapshot,
    ChannelDelivery,
    ContactEndpoint,
    NotificationCampaign,
    NotificationIntent,
    NotificationMessage,
    NotificationOutbox,
    NotificationTemplate,
)
from notification_center.security import decrypt_sensitive
from notification_center.serializers import NotificationMessageSerializer
from notification_center.services import NotificationCenterService, _SendResult

User = get_user_model()


class NotificationCenterServiceTests(TestCase):
    def test_sms_delivery_query_result_accepts_delivered_at(self):
        delivered_at = timezone.now()
        result = SMSDeliveryQueryResult(
            normalized_status="delivered",
            biz_id="biz-final",
            delivered_at=delivered_at,
        )

        self.assertEqual(result.delivered_at, delivered_at)

    @patch("notification_center.tasks.relay_notification_outbox_task.delay")
    @patch("notification_center.services.AliyunSMSProvider.send_login_code")
    @patch("notification_center.services.AliyunSMSProvider.otp_readiness_error", return_value="")
    def test_phone_otp_is_queued_without_synchronous_provider_call(self, _readiness, send_login_code, relay_delay):
        with self.captureOnCommitCallbacks(execute=True):
            ok, reason, message_id = NotificationCenterService.send_phone_otp(
                phone_number="+8613800138001",
                code="123456",
                request_id="req-otp-queue",
                otp_id="otp-queue",
                ip_address="127.0.0.1",
                expires_at=timezone.now() + timedelta(minutes=5),
                dispatch_sync=False,
            )

        self.assertTrue(ok)
        self.assertEqual(reason, "")
        send_login_code.assert_not_called()
        relay_delay.assert_called_once()
        message = NotificationMessage.objects.get(id=int(message_id))
        self.assertEqual(message.status, NotificationMessage.Status.QUEUED)
        self.assertTrue(message.intent.sensitive_context_ciphertext.startswith("v1:"))
        self.assertTrue(NotificationOutbox.objects.filter(aggregate_id=str(message.intent_id), status=NotificationOutbox.Status.PENDING).exists())

    @patch("notification_center.services.AliyunSMSProvider.query_send_details")
    @patch("notification_center.services.time_module.sleep", return_value=None)
    @patch("notification_center.services.AliyunSMSProvider.send_login_code")
    @patch("notification_center.services.AliyunSMSProvider.otp_readiness_error", return_value="")
    def test_phone_otp_records_business_scene_without_plain_code(self, _readiness, mocked_send, _sleep, mocked_query):
        user = User.objects.create_user(username="scene-user", password="x")
        mocked_send.return_value = SMSProviderResult(
            accepted=True,
            unknown=False,
            reason="",
            biz_id="biz-scene",
            request_id="provider-scene",
            code="OK",
            status="accepted",
            payload={},
        )
        mocked_query.return_value = SMSDeliveryQueryResult(
            normalized_status="delivered",
            biz_id="biz-scene",
            request_id="provider-query-scene",
            code="OK",
            provider_status="3",
            payload={"send_status": "3", "err_code": "DELIVERED"},
            delivered_at=timezone.now(),
        )

        ok, _, message_id = NotificationCenterService.send_phone_otp(
            phone_number="+8613800138005",
            code="123456",
            request_id="req-scene",
            otp_id="otp-scene",
            ip_address="127.0.0.1",
            user_id=user.id,
            scene="login",
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        self.assertTrue(ok)
        message = NotificationMessage.objects.select_related("intent", "user").get(id=int(message_id))
        self.assertEqual(message.user_id, user.id)
        self.assertEqual(message.intent.business_scene, "account.auth.login_otp_requested")
        self.assertEqual(message.intent.business_domain, "account")
        self.assertEqual(message.intent.business_type, "account.auth")
        self.assertEqual(message.body, "")
        self.assertEqual(message.payload["business_scene"], "account.auth.login_otp_requested")
        self.assertNotIn("123456", message.body)

    @patch("notification_center.services.cache.incr", return_value=6)
    @patch("notification_center.services.cache.add", return_value=True)
    @patch("notification_center.services.AliyunSMSProvider.send_login_code")
    @patch("notification_center.services.AliyunSMSProvider.otp_readiness_error", return_value="")
    def test_phone_otp_rate_limit_blocks_before_provider(self, _readiness, send_login_code, _cache_add, _cache_incr):
        ok, reason, _ = NotificationCenterService.send_phone_otp(
            phone_number="+8613800138002",
            code="123456",
            request_id="req-otp-limit",
            otp_id="otp-limit",
            ip_address="127.0.0.1",
        )

        self.assertFalse(ok)
        self.assertEqual(reason, "otp_rate_limited")
        send_login_code.assert_not_called()

    @patch("notification_center.services.AliyunSMSProvider.query_send_details")
    @patch("notification_center.services.time_module.sleep", return_value=None)
    @patch("notification_center.tasks.relay_notification_outbox_task.delay")
    @patch("notification_center.services.AliyunSMSProvider.send_login_code")
    @patch("notification_center.services.AliyunSMSProvider.otp_readiness_error", return_value="")
    def test_phone_otp_worker_sends_and_clears_sensitive_context(self, _readiness, send_login_code, _relay_delay, _sleep, mocked_query):
        send_login_code.return_value = SMSProviderResult(
            accepted=True,
            unknown=False,
            reason="",
            biz_id="biz-otp",
            request_id="provider-req",
            code="OK",
            status="accepted",
        )
        mocked_query.return_value = SMSDeliveryQueryResult(
            normalized_status="delivered",
            biz_id="biz-otp",
            request_id="provider-query-otp",
            code="OK",
            provider_status="3",
            payload={"send_status": "3", "err_code": "DELIVERED"},
            delivered_at=timezone.now(),
        )
        ok, _, message_id = NotificationCenterService.send_phone_otp(
            phone_number="+8613800138003",
            code="123456",
                request_id="req-otp-worker",
                otp_id="otp-worker",
                ip_address="127.0.0.1",
                dispatch_sync=False,
            )
        self.assertTrue(ok)
        message = NotificationMessage.objects.select_related("intent").get(id=int(message_id))

        result = NotificationCenterService.execute_phone_otp_intent(intent_id=message.intent_id, message_id=message.id)

        message.refresh_from_db()
        message.intent.refresh_from_db()
        self.assertEqual(result["status"], ChannelDelivery.Status.DELIVERED)
        self.assertEqual(message.status, NotificationMessage.Status.DELIVERED)
        self.assertEqual(message.intent.sensitive_context_ciphertext, "")
        delivery = ChannelDelivery.objects.get(message=message, channel=ChannelDelivery.Channel.SMS)
        self.assertEqual(delivery.details["template_param"]["code"], "123456")
        data = NotificationMessageSerializer(message).data
        self.assertEqual(data["payload"]["sms_send_request"]["template_param"]["code"], "123456")
        self.assertEqual(data["delivery_details"][0]["template_param"]["code"], "123456")
        self.assertEqual(NotificationOutbox.objects.get(aggregate_id=str(message.intent_id)).status, NotificationOutbox.Status.PROCESSED)

    @patch("notification_center.services.AliyunSMSProvider.query_send_details")
    @patch("notification_center.services.time_module.sleep", return_value=None)
    @patch("notification_center.services.AliyunSMSProvider.send_login_code")
    @patch("notification_center.services.AliyunSMSProvider.otp_readiness_error", return_value="")
    def test_phone_otp_sync_request_fails_when_receipt_times_out(self, _readiness, send_login_code, mocked_sleep, mocked_query):
        send_login_code.return_value = SMSProviderResult(
            accepted=True,
            unknown=False,
            reason="",
            biz_id="biz-timeout",
            request_id="provider-timeout",
            code="OK",
            status="accepted",
            payload={},
        )
        mocked_query.return_value = SMSDeliveryQueryResult(
            normalized_status="accepted",
            biz_id="biz-timeout",
            request_id="provider-query-timeout",
            code="OK",
            provider_status="accepted",
            payload={"total_count": 0, "detail_count": 0},
        )

        ok, reason, message_id = NotificationCenterService.send_phone_otp(
            phone_number="+8613800138006",
            code="654321",
            request_id="req-timeout",
            otp_id="otp-timeout",
            ip_address="127.0.0.1",
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        self.assertFalse(ok)
        self.assertEqual(reason, "sms_receipt_timeout")
        self.assertEqual(mocked_query.call_count, 10)
        self.assertEqual(mocked_sleep.call_count, 10)
        message = NotificationMessage.objects.get(id=int(message_id))
        delivery = ChannelDelivery.objects.get(message=message, channel=ChannelDelivery.Channel.SMS)
        self.assertEqual(delivery.status, ChannelDelivery.Status.SUBMIT_UNKNOWN)
        self.assertEqual(delivery.error_code, "sms_receipt_timeout")

    @patch("notification_center.tasks.relay_notification_outbox_task.delay")
    def test_campaign_uses_row_based_audience_snapshot(self, _relay_delay):
        user = User.objects.create_user(username="audience-user", password="x")
        campaign = NotificationCenterService.create_campaign_and_enqueue(
            channels=[NotificationMessage.Channel.EMAIL],
            title="title",
            body="body",
            payload={},
            user_id=user.id,
            user_ids=[],
            filters={},
            template_id=None,
            schedule_at=None,
            campaign_name="snapshot",
            created_by_id=None,
            request_id="req-audience",
        )

        campaign.refresh_from_db()
        self.assertEqual(campaign.target_user_ids, [])
        self.assertTrue(AudienceSnapshot.objects.filter(campaign=campaign, user=user, status=AudienceSnapshot.Status.INCLUDED).exists())

    def test_stuck_running_campaign_is_requeued_with_outbox(self):
        intent = NotificationIntent.objects.create(topic_key="test", idempotency_key="stuck-intent")
        campaign = NotificationCampaign.objects.create(name="stuck", status=NotificationCampaign.Status.RUNNING, intent=intent)
        row = NotificationOutbox.objects.create(
            aggregate_type="notification_campaign",
            aggregate_id=str(campaign.id),
            event_type="notification.campaign.dispatch",
            payload={"campaign_id": campaign.id},
            idempotency_key="stuck-outbox",
            status=NotificationOutbox.Status.PROCESSING,
        )
        NotificationOutbox.objects.filter(id=row.id).update(updated_at=timezone.now() - timedelta(minutes=10))

        self.assertEqual(NotificationCenterService.requeue_stuck_outbox(stale_seconds=60), 1)
        campaign.refresh_from_db()
        row.refresh_from_db()
        self.assertEqual(campaign.status, NotificationCampaign.Status.QUEUED)
        self.assertEqual(row.status, NotificationOutbox.Status.PENDING)

    def test_ensure_endpoint_encrypts_sensitive_address(self):
        endpoint = NotificationCenterService._ensure_endpoint(
            user=None,
            channel=ContactEndpoint.Channel.SMS,
            address="+8613800138000",
            metadata={"request_id": "req-1"},
        )

        self.assertNotEqual(endpoint.address_ciphertext, "+8613800138000")
        self.assertEqual(decrypt_sensitive(endpoint.address_ciphertext), "+8613800138000")
        self.assertEqual(endpoint.address_masked, "861****8000")

    def test_record_message_event_keeps_sms_submission_as_accepted_not_delivered(self):
        user = User.objects.create_user(username="notify-a", password="x")
        endpoint = NotificationCenterService._ensure_endpoint(
            user=user,
            channel=ContactEndpoint.Channel.SMS,
            address="+8613800138000",
            metadata={"request_id": "req-accepted"},
        )
        message = NotificationMessage.objects.create(
            user=user,
            recipient_type=NotificationMessage.RecipientType.USER,
            recipient_key=str(user.id),
            channel=NotificationMessage.Channel.SMS,
            status=NotificationMessage.Status.SENT,
            title="t",
            body="b",
            request_id="req-accepted",
        )

        NotificationCenterService._record_message_event(
            message=message,
            channel=NotificationMessage.Channel.SMS,
            provider="aliyun",
            result=_SendResult(
                accepted=True,
                delivered=False,
                unknown=False,
                skipped=False,
                reason="",
                provider_message_id="biz-1",
                provider_request_id="req-accepted",
                provider_code="OK",
                provider_status="accepted",
            ),
            endpoint=endpoint,
            details=[],
        )

        message.refresh_from_db()
        delivery = ChannelDelivery.objects.get(message=message)
        self.assertIsNone(message.delivered_at)
        self.assertEqual(delivery.status, ChannelDelivery.Status.ACCEPTED)
        self.assertIsNone(delivery.delivered_at)

    def test_send_sms_without_phone_is_skipped(self):
        user = User.objects.create_user(username="notify-b", password="x")

        message = NotificationCenterService._send_sms(
            campaign_id=None,
            user=user,
            title="t",
            body="b",
            payload={},
            created_by_id=None,
            request_id="req-skip",
            topic_key="security.otp",
        )

        delivery = ChannelDelivery.objects.get(message=message)
        self.assertEqual(message.status, NotificationMessage.Status.SKIPPED)
        self.assertEqual(delivery.status, ChannelDelivery.Status.CANCELLED)

    def test_template_version_snapshot_controls_rendering(self):
        user = User.objects.create_user(username="notify-c", password="x", email="demo@example.com")
        template = NotificationTemplate.objects.create(
            key="tpl-1",
            name="模板",
            topic_key="marketing.campaign",
            title_template="old {username}",
            body_template="old body",
            payload_template={"kind": "old"},
        )
        version = NotificationCenterService.publish_template_snapshot(template=template)
        template.title_template = "new {username}"
        template.body_template = "new body"
        template.payload_template = {"kind": "new"}
        template.save(update_fields=["title_template", "body_template", "payload_template", "updated_at"])

        title, body, payload = NotificationCenterService.build_message_content(
            user=user,
            template=template,
            template_version=version,
            title="fallback",
            body="fallback",
            payload={"extra": "yes"},
        )

        self.assertEqual(title, "old notify-c")
        self.assertEqual(body, "old body")
        self.assertEqual(payload, {"kind": "old", "extra": "yes"})

    def test_poll_pending_sms_deliveries_updates_final_status(self):
        user = User.objects.create_user(username="notify-d", password="x")
        sent_at = datetime(2026, 7, 12, 21, 22, 23, tzinfo=dt_timezone.utc)
        endpoint = NotificationCenterService._ensure_endpoint(
            user=user,
            channel=ContactEndpoint.Channel.SMS,
            address="+8613800138000",
            metadata={"request_id": "req-poll"},
        )
        message = NotificationMessage.objects.create(
            user=user,
            recipient_type=NotificationMessage.RecipientType.USER,
            recipient_key=str(user.id),
            channel=NotificationMessage.Channel.SMS,
            status=NotificationMessage.Status.SENT,
            title="t",
            body="b",
            receiver_phone=endpoint.address_masked,
            provider_message_id="biz-2",
            request_id="req-poll",
            sent_at=sent_at,
        )
        delivery = ChannelDelivery.objects.create(
            message=message,
            channel=ChannelDelivery.Channel.SMS,
            provider="aliyun",
            status=ChannelDelivery.Status.ACCEPTED,
            endpoint_type=ContactEndpoint.Channel.SMS,
            endpoint_hmac=endpoint.address_hmac,
            endpoint_masked=endpoint.address_masked,
            provider_message_id="biz-2",
        )

        with patch("notification_center.services.AliyunSMSProvider.query_send_details") as mocked:
            mocked.return_value = SMSDeliveryQueryResult(
                normalized_status="delivered",
                biz_id="biz-2",
                request_id="req-poll",
                code="OK",
                provider_status="3",
                payload={"send_status": "3"},
            )
            result = NotificationCenterService.poll_pending_sms_deliveries()

        delivery.refresh_from_db()
        message.refresh_from_db()
        self.assertEqual(result["delivered"], 1)
        self.assertEqual(delivery.status, ChannelDelivery.Status.DELIVERED)
        self.assertEqual(message.provider_status, "3")
        mocked.assert_called_once()
        self.assertEqual(
            mocked.call_args.kwargs["send_date"],
            timezone.localtime(sent_at, timezone=ZoneInfo("Asia/Shanghai")),
        )

    def test_sms_receipt_query_phone_uses_mainland_11_digits(self):
        self.assertEqual(NotificationCenterService._sms_receipt_query_phone("+8615385056020"), "15385056020")
        self.assertEqual(NotificationCenterService._sms_receipt_query_phone("15385056020"), "15385056020")

    @patch("notification_center.services.logger")
    @patch("notification_center.services.AliyunSMSProvider.query_send_details")
    def test_query_sms_send_details_logs_and_passes_request_id(self, mocked_query, mocked_logger):
        endpoint = NotificationCenterService._ensure_endpoint(
            user=None,
            channel=ContactEndpoint.Channel.SMS,
            address="+8613800138004",
            metadata={"request_id": "req-query-1"},
        )
        sent_at = datetime(2026, 7, 12, 21, 22, 23, tzinfo=dt_timezone.utc)
        message = NotificationMessage.objects.create(
            recipient_type=NotificationMessage.RecipientType.CONTACT,
            recipient_key="+8613800138004",
            channel=NotificationMessage.Channel.SMS,
            status=NotificationMessage.Status.ACCEPTED,
            title="验证码短信",
            body="123456",
            sent_at=sent_at,
        )
        delivery = ChannelDelivery.objects.create(
            message=message,
            channel=ChannelDelivery.Channel.SMS,
            provider="aliyun",
            status=ChannelDelivery.Status.ACCEPTED,
            endpoint_type=ContactEndpoint.Channel.SMS,
            endpoint_hmac=endpoint.address_hmac,
            endpoint_masked=endpoint.address_masked,
            provider_message_id="biz-query-1",
        )
        mocked_query.return_value = SMSDeliveryQueryResult(
            normalized_status="accepted",
            biz_id="biz-query-1",
            request_id="provider-query-1",
            code="OK",
            provider_status="accepted",
            payload={"send_status": "1"},
        )

        row = NotificationCenterService.query_sms_send_details_for_message(
            message_id=message.id,
            request_id="req-query-1",
            operator_user_id=1,
        )

        self.assertEqual(row.id, message.id)
        mocked_query.assert_called_once()
        self.assertEqual(mocked_query.call_args.kwargs["request_id"], "req-query-1")
        self.assertEqual(
            mocked_query.call_args.kwargs["send_date"],
            timezone.localtime(sent_at, timezone=ZoneInfo("Asia/Shanghai")),
        )
        mocked_logger.info.assert_any_call(
            "notification.sms.query_send_details.begin message_id=%s delivery_id=%s biz_id=%s phone_number=%s send_date=%s operator_user_id=%s",
            message.id,
            delivery.id,
            "biz-query-1",
            "13800138004",
            timezone.localtime(sent_at, timezone=ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d"),
            1,
            extra={
                "action": "notification.sms.query_send_details",
                "request_id": "req-query-1",
                "message_id": message.id,
                "delivery_id": delivery.id,
                "operator_user_id": 1,
                "biz_id": "biz-query-1",
                "phone_number": "13800138004",
                "send_date": timezone.localtime(sent_at, timezone=ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d"),
                "send_date_source": "message.sent_at",
            },
        )

    def test_sms_receipt_query_send_date_prefers_sent_at_and_business_timezone(self):
        user = User.objects.create_user(username="notify-f", password="x")
        sent_at = datetime(2026, 7, 12, 21, 22, 23, tzinfo=dt_timezone.utc)
        message = NotificationMessage.objects.create(
            user=user,
            recipient_type=NotificationMessage.RecipientType.CONTACT,
            recipient_key="+8613800138009",
            channel=NotificationMessage.Channel.SMS,
            status=NotificationMessage.Status.ACCEPTED,
            title="通知",
            body="b",
            sent_at=sent_at,
        )
        delivery = ChannelDelivery.objects.create(
            message=message,
            channel=ChannelDelivery.Channel.SMS,
            provider="aliyun",
            status=ChannelDelivery.Status.ACCEPTED,
        )

        query_send_date = NotificationCenterService._sms_receipt_query_send_date(delivery)

        self.assertEqual(
            query_send_date,
            timezone.localtime(sent_at, timezone=ZoneInfo("Asia/Shanghai")),
        )

    def test_message_serializer_shows_full_sms_phone_and_code_for_internal_admin(self):
        user = User.objects.create_user(username="notify-e", password="x")
        endpoint = NotificationCenterService._ensure_endpoint(
            user=user,
            channel=ContactEndpoint.Channel.SMS,
            address="+8613800138000",
            metadata={"request_id": "req-full-phone"},
        )
        message = NotificationMessage.objects.create(
            user=user,
            recipient_type=NotificationMessage.RecipientType.CONTACT,
            recipient_key=endpoint.address_hmac,
            channel=NotificationMessage.Channel.SMS,
            status=NotificationMessage.Status.SENT,
            title="通知",
            body="abcdef" * 40,
            payload={"code": "123456", "scene": "login"},
            receiver_phone="861****8000",
        )

        data = NotificationMessageSerializer(message).data
        self.assertEqual(data["recipient_key"], "+8613800138000")
        self.assertEqual(data["masked_phone"], "+8613800138000")
        self.assertEqual(data["body"], "")
        self.assertEqual(data["payload"], {"code": "123456"})

    @patch("notification_center.services.AliyunSMSProvider.query_send_details")
    def test_query_sms_send_details_keeps_submit_status_accepted_when_receipt_failed(self, mocked_query):
        endpoint = NotificationCenterService._ensure_endpoint(
            user=None,
            channel=ContactEndpoint.Channel.SMS,
            address="+8618255099136",
            metadata={"request_id": "req-query-failed-receipt"},
        )
        message = NotificationMessage.objects.create(
            recipient_type=NotificationMessage.RecipientType.CONTACT,
            recipient_key=endpoint.address_hmac,
            channel=NotificationMessage.Channel.SMS,
            status=NotificationMessage.Status.ACCEPTED,
            title="验证码短信",
            body="",
            sent_at=timezone.now(),
            provider_message_id="biz-failed-receipt",
            provider_code="OK",
            provider_status="accepted",
        )
        ChannelDelivery.objects.create(
            message=message,
            channel=ChannelDelivery.Channel.SMS,
            provider="aliyun",
            status=ChannelDelivery.Status.ACCEPTED,
            endpoint_type=ContactEndpoint.Channel.SMS,
            endpoint_hmac=endpoint.address_hmac,
            endpoint_masked=endpoint.address_masked,
            provider_message_id="biz-failed-receipt",
            provider_code="OK",
            provider_status="accepted",
            accepted_at=timezone.now(),
            details={
                "code": "OK",
                "message": "OK",
                "biz_id": "biz-failed-receipt",
                "template_code": "SMS_508370089",
                "template_param_keys": ["code"],
                "template_param": {"code": "864201"},
                "phone_number_masked": "861****9136",
            },
        )
        mocked_query.return_value = SMSDeliveryQueryResult(
            normalized_status="delivery_failed",
            biz_id="biz-failed-receipt",
            request_id="provider-query-failed-receipt",
            code="MOBILE_SEND_LIMIT",
            provider_status="2",
            reason="MOBILE_SEND_LIMIT",
            payload={
                "send_status": "2",
                "err_code": "MOBILE_SEND_LIMIT",
                "biz_id": "biz-failed-receipt",
                "request_id": "provider-query-failed-receipt",
            },
        )

        row = NotificationCenterService.query_sms_send_details_for_message(message_id=message.id)
        data = NotificationMessageSerializer(row).data

        self.assertEqual(data["submit_status"], "accepted")
        self.assertEqual(data["delivery_status"], "failed")
        self.assertEqual(data["payload"], {"code": "864201"})
        self.assertEqual(data["delivery_details"][0]["template_param"]["code"], "864201")
        self.assertNotEqual(data["payload"], {})
        self.assertNotEqual(data["delivery_details"], [])

    def test_provider_accepted_does_not_meet_delivered_threshold(self):
        self.assertTrue(
            NotificationCenterService._delivery_meets_threshold(
                SimpleNamespace(status=ChannelDelivery.Status.ACCEPTED),
                "provider_accepted",
            )
        )
        self.assertFalse(
            NotificationCenterService._delivery_meets_threshold(
                SimpleNamespace(status=ChannelDelivery.Status.ACCEPTED),
                "provider_delivered",
            )
        )
        self.assertTrue(
            NotificationCenterService._delivery_meets_threshold(
                SimpleNamespace(status=ChannelDelivery.Status.DELIVERED),
                "provider_delivered",
            )
        )

    @patch("accounts.infrastructure.sms_provider.AliyunSMSProvider._build_client")
    @patch(
        "accounts.infrastructure.sms_provider.util_models",
        new=SimpleNamespace(RuntimeOptions=lambda: SimpleNamespace()),
    )
    @patch(
        "accounts.infrastructure.sms_provider.dysms_models",
        new=SimpleNamespace(QuerySendDetailsRequest=lambda **kwargs: SimpleNamespace(**kwargs)),
    )
    def test_aliyun_sms_query_send_details_normalizes_send_date_to_shanghai(self, mocked_build_client):
        detail = SimpleNamespace(
            send_status="3",
            err_code="DELIVERED",
            receive_date="2026-07-13 05:22:29",
        )
        response = SimpleNamespace(
            status_code=200,
            body=SimpleNamespace(
                code="OK",
                message="OK",
                request_id="provider-query-1",
                total_count=1,
                sms_send_detail_dtos=SimpleNamespace(sms_send_detail_dto=[detail]),
            ),
        )

        class FakeClient:
            def __init__(self):
                self.request = None

            def query_send_details_with_options(self, request, runtime):
                self.request = request
                return response

        fake_client = FakeClient()
        mocked_build_client.return_value = fake_client
        send_date = datetime(2026, 7, 12, 21, 22, 23, tzinfo=dt_timezone.utc)

        query_result = AliyunSMSProvider.query_send_details(
            phone_number="+8615385056020",
            biz_id="biz-1",
            send_date=send_date,
        )

        self.assertEqual(fake_client.request.send_date, "20260713")
        self.assertEqual(query_result.normalized_status, "delivered")
