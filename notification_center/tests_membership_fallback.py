from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.infrastructure.sms_provider import SMSProviderResult
from accounts.models import SocialIdentity
from notification_center.business_scenes import MEMBERSHIP_FALLBACK_ROUTING, sync_business_scenes
from notification_center.models import (
    ChannelDelivery,
    NotificationBusinessScene,
    NotificationIntent,
    NotificationMessage,
    NotificationRecipientMessage,
)
from notification_center.services import NotificationCenterService, _SendResult

User = get_user_model()


class MembershipFallbackRoutingCatalogTests(TestCase):
    def setUp(self):
        sync_business_scenes()

    def test_application_approved_uses_fallback_routing(self):
        scene = NotificationBusinessScene.objects.get(key="membership.pro_trial.application_approved")
        self.assertEqual(scene.default_routing["mode"], "fallback")
        self.assertEqual(
            [step["channel"] for step in scene.default_routing["steps"]],
            ["apns", "email", "sms"],
        )

    def test_manually_granted_display_name_and_routing(self):
        scene = NotificationBusinessScene.objects.get(key="membership.pro_trial.manually_granted")
        self.assertEqual(scene.display_name, "系统发放试用")
        self.assertEqual(scene.default_routing, MEMBERSHIP_FALLBACK_ROUTING)


class MembershipFallbackSendTests(TestCase):
    def setUp(self):
        sync_business_scenes()
        self.user = User.objects.create_user(
            username="membership-fallback",
            password="x",
            email="member@example.com",
        )
        SocialIdentity.objects.create(
            user=self.user,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8613800138000",
            bundle_id="com.example.app",
        )
        self.device = SimpleNamespace(
            push_token="806a03abcdef1234567890abcdef2386b2",
            bundle_id="com.example.app",
            bundle_identifier="com.example.app",
            device_id="device-1",
            notifications_enabled=True,
            is_revoked=False,
        )
        self.send_kwargs = dict(
            campaign_id=None,
            user_id=self.user.id,
            title="试用通知",
            body="body",
            payload={"type": "membership_pro_trial"},
            created_by_id=None,
            request_id="membership-fallback-test",
            business_scene="membership.pro_trial.manually_granted",
            business_reference_type="trial_application",
            business_id="99",
            idempotency_key="membership.pro_trial.manually_granted:99:test",
            source="unit-test",
        )

    @patch("notification_center.services.AliyunSMSProvider.send")
    @patch("notification_center.services.EmailProvider.send_notification")
    @patch("notification_center.services.APNsProvider.send")
    @patch("notification_center.services.DeviceSessionService.apns_trusted_device_for_user")
    def test_apns_success_stops_before_email_and_sms(self, apns_device, apns_send, email_send, sms_send):
        apns_device.return_value = self.device
        apns_send.return_value = (True, "", "apns-1")

        messages = NotificationCenterService.send_to_user_sync(
            channels=[NotificationMessage.Channel.APNS],
            **self.send_kwargs,
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].channel, NotificationMessage.Channel.APNS)
        email_send.assert_not_called()
        sms_send.assert_not_called()
        recipient = NotificationRecipientMessage.objects.get(recipient_key=str(self.user.id))
        self.assertEqual(recipient.status, NotificationRecipientMessage.Status.ACCEPTED)

    @patch("notification_center.services.AliyunSMSProvider.send")
    @patch("notification_center.services.EmailProvider.send_notification")
    @patch("notification_center.services.APNsProvider.send")
    @patch("notification_center.services.DeviceSessionService.apns_trusted_device_for_user")
    def test_apns_failure_falls_back_to_email(self, apns_device, apns_send, email_send, sms_send):
        apns_device.return_value = self.device
        apns_send.return_value = (False, "apns_unavailable", "")
        email_send.return_value = (True, "", "email-1", "")

        messages = NotificationCenterService.send_to_user_sync(
            channels=[NotificationMessage.Channel.APNS],
            **self.send_kwargs,
        )

        self.assertEqual(len(messages), 2)
        self.assertEqual([message.channel for message in messages], ["apns", "email"])
        email_send.assert_called_once()
        sms_send.assert_not_called()
        recipient = NotificationRecipientMessage.objects.get(recipient_key=str(self.user.id))
        self.assertEqual(recipient.status, NotificationRecipientMessage.Status.ACCEPTED)

    @patch("notification_center.services.AliyunSMSProvider.send")
    @patch("notification_center.services.EmailProvider.send_notification")
    @patch("notification_center.services.DeviceSessionService.apns_trusted_device_for_user")
    def test_apns_and_email_failure_fall_back_to_sms(self, apns_device, email_send, sms_send):
        apns_device.return_value = None
        email_send.return_value = (False, "smtp_error", "", "connection refused")
        sms_send.return_value = SMSProviderResult(
            accepted=True,
            unknown=False,
            biz_id="sms-1",
            request_id="req-sms",
            code="OK",
            status="accepted",
            reason="",
            payload={},
        )

        messages = NotificationCenterService.send_to_user_sync(
            channels=[NotificationMessage.Channel.APNS],
            **self.send_kwargs,
        )

        self.assertEqual(len(messages), 3)
        self.assertEqual([message.channel for message in messages], ["apns", "email", "sms"])
        sms_send.assert_called_once()
        recipient = NotificationRecipientMessage.objects.get(recipient_key=str(self.user.id))
        self.assertEqual(recipient.status, NotificationRecipientMessage.Status.ACCEPTED)

    @patch("notification_center.services.AliyunSMSProvider.send")
    @patch("notification_center.services.EmailProvider.send_notification")
    @patch("notification_center.services.DeviceSessionService.apns_trusted_device_for_user")
    def test_all_channels_fail_marks_recipient_failed(self, apns_device, email_send, sms_send):
        apns_device.return_value = None
        email_send.return_value = (False, "smtp_error", "", "connection refused")
        sms_send.return_value = SMSProviderResult(
            accepted=False,
            unknown=False,
            biz_id="",
            request_id="req-sms",
            code="ERROR",
            status="failed",
            reason="sms_failed",
            payload={},
        )

        messages = NotificationCenterService.send_to_user_sync(
            channels=[NotificationMessage.Channel.APNS],
            **self.send_kwargs,
        )

        self.assertEqual(len(messages), 3)
        recipient = NotificationRecipientMessage.objects.get(recipient_key=str(self.user.id))
        self.assertEqual(recipient.status, NotificationRecipientMessage.Status.FAILED)
        deliveries = ChannelDelivery.objects.filter(message__recipient_message=recipient)
        self.assertEqual(deliveries.filter(channel=ChannelDelivery.Channel.APNS).first().status, ChannelDelivery.Status.CANCELLED)
        self.assertEqual(deliveries.filter(channel=ChannelDelivery.Channel.EMAIL).first().status, ChannelDelivery.Status.SUBMIT_FAILED)
        self.assertEqual(deliveries.filter(channel=ChannelDelivery.Channel.SMS).first().status, ChannelDelivery.Status.SUBMIT_FAILED)

    @patch("notification_center.services.NotificationCenterService._send_email")
    @patch("notification_center.services.NotificationCenterService._send_apns")
    def test_submit_unknown_does_not_fallback_to_email(self, send_apns, send_email):
        message = NotificationMessage.objects.create(
            user_id=self.user.id,
            recipient_type=NotificationMessage.RecipientType.USER,
            recipient_key=str(self.user.id),
            channel=NotificationMessage.Channel.APNS,
            status=NotificationMessage.Status.PROCESSING,
            title="t",
            body="b",
            payload={},
            request_id="membership-fallback-test",
        )
        NotificationCenterService._record_message_event(
            message=message,
            channel=NotificationMessage.Channel.APNS,
            provider="apns",
            result=_SendResult(
                accepted=False,
                delivered=False,
                unknown=True,
                skipped=False,
                reason="timeout",
                provider_message_id="",
                provider_request_id="membership-fallback-test",
            ),
        )
        send_apns.return_value = message

        messages = NotificationCenterService.send_to_user_sync(
            channels=[NotificationMessage.Channel.APNS],
            **self.send_kwargs,
        )

        self.assertEqual(len(messages), 1)
        send_email.assert_not_called()
        recipient = NotificationRecipientMessage.objects.get(recipient_key=str(self.user.id))
        self.assertEqual(recipient.status, NotificationRecipientMessage.Status.PROCESSING)

    def test_suppressed_expiring_scene_creates_no_intent(self):
        before = NotificationIntent.objects.count()
        messages = NotificationCenterService.send_to_user_sync(
            campaign_id=None,
            user_id=self.user.id,
            channels=[NotificationMessage.Channel.APNS],
            title="即将到期",
            body="body",
            payload={},
            created_by_id=None,
            request_id="expiring-suppressed",
            business_scene="membership.pro_trial.expiring",
            business_reference_type="trial",
            business_id="1",
            idempotency_key="membership.pro_trial.expiring:1:test",
            source="unit-test",
        )
        self.assertEqual(messages, [])
        self.assertEqual(NotificationIntent.objects.count(), before)
        self.assertFalse(NotificationMessage.objects.filter(request_id="expiring-suppressed").exists())

    def test_suppressed_revoked_scene_creates_no_intent(self):
        before = NotificationIntent.objects.count()
        messages = NotificationCenterService.send_to_user_sync(
            campaign_id=None,
            user_id=self.user.id,
            channels=[NotificationMessage.Channel.APNS],
            title="试用收回",
            body="body",
            payload={},
            created_by_id=None,
            request_id="revoked-suppressed",
            business_scene="membership.pro_trial.revoked",
            business_reference_type="trial",
            business_id="1",
            idempotency_key="membership.pro_trial.revoked:1:test",
            source="unit-test",
        )
        self.assertEqual(messages, [])
        self.assertEqual(NotificationIntent.objects.count(), before)
