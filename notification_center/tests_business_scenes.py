from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from django.contrib.auth import get_user_model

from notification_center.business_scenes import SCENE_CATALOG, sync_business_scenes
from notification_center.models import NotificationBusinessScene, NotificationMessage, NotificationOutbox
from notification_center.services import NotificationCenterService

User = get_user_model()


class NotificationBusinessSceneModelTests(TestCase):
    def test_scene_key_must_match_domain_type_and_event(self):
        scene = NotificationBusinessScene(
            key="medical.resource.fixture_updated",
            domain="account",
            business_type="medical.wrong",
            event_name="created",
            display_name="医疗信息已更新",
            category=NotificationBusinessScene.Category.TRANSACTIONAL,
        )

        with self.assertRaises(ValidationError) as raised:
            scene.full_clean()

        self.assertEqual(set(raised.exception.message_dict), {"domain", "business_type", "event_name"})

    def test_invalid_free_text_scene_key_is_rejected(self):
        scene = NotificationBusinessScene(
            key="Medical Update",
            domain="Medical Update",
            business_type="Medical Update",
            event_name="Medical Update",
            display_name="invalid",
            category=NotificationBusinessScene.Category.TRANSACTIONAL,
        )
        with self.assertRaises(ValidationError):
            scene.full_clean()


class NotificationBusinessSceneRegistryTests(TestCase):
    def test_sync_is_idempotent_and_projects_all_catalog_fields(self):
        NotificationBusinessScene.objects.all().delete()

        created, updated = sync_business_scenes()
        created_again, updated_again = sync_business_scenes()

        self.assertEqual(created, len(SCENE_CATALOG))
        self.assertEqual(updated, 0)
        self.assertEqual(created_again, 0)
        self.assertEqual(updated_again, len(SCENE_CATALOG))
        scene = NotificationBusinessScene.objects.get(key="membership.pro_trial.application_approved")
        self.assertEqual(scene.domain, "membership")
        self.assertEqual(scene.business_type, "membership.pro_trial")
        self.assertEqual(scene.event_name, "application_approved")
        self.assertEqual(scene.status, NotificationBusinessScene.Status.ACTIVE)

    def test_command_synchronizes_catalog(self):
        NotificationBusinessScene.objects.all().delete()
        output = StringIO()
        call_command("sync_notification_scenes", stdout=output)
        self.assertEqual(NotificationBusinessScene.objects.count(), len(SCENE_CATALOG))
        self.assertIn("notification scenes synchronized", output.getvalue())

    def test_unknown_scene_is_not_created_at_runtime(self):
        with self.assertRaisesMessage(ValueError, "business_scene_not_registered"):
            NotificationCenterService.ensure_business_scene("account.auth.typo_requested")
        self.assertFalse(NotificationBusinessScene.objects.filter(key="account.auth.typo_requested").exists())

    def test_retired_scene_cannot_be_used(self):
        scene = NotificationCenterService.ensure_business_scene("medical.resource.updated")
        scene.status = NotificationBusinessScene.Status.RETIRED
        scene.save(update_fields=["status", "updated_at"])
        with self.assertRaisesMessage(ValueError, "business_scene_not_active"):
            NotificationCenterService.ensure_business_scene("medical.resource.updated")

    def test_direct_user_send_requires_business_scene(self):
        user = User.objects.create_user(username="scene-required", password="x")

        with self.assertRaisesMessage(ValueError, "business_scene_required"):
            NotificationCenterService.send_to_user_sync(
                campaign_id=None,
                user_id=user.id,
                channels=[NotificationMessage.Channel.APNS],
                title="t",
                body="b",
                payload={},
                created_by_id=None,
                request_id="scene-required",
            )

    def test_direct_user_send_attaches_scene_intent(self):
        user = User.objects.create_user(username="scene-attached", password="x")

        messages = NotificationCenterService.send_to_user_sync(
            campaign_id=None,
            user_id=user.id,
            channels=[NotificationMessage.Channel.APNS],
            title="医疗信息已更新",
            body="你的医疗信息有更新",
            payload={"resource_type": "medication_plan", "resource_id": "1"},
            created_by_id=None,
            request_id="scene-attached",
            business_scene="medical.resource.updated",
            business_reference_type="medication_plan",
            business_id="1",
            idempotency_key="medical.resource.updated:medication_plan:1:user",
            source="unit-test",
        )

        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertIsNotNone(message.intent_id)
        self.assertEqual(message.intent.business_scene, "medical.resource.updated")
        self.assertEqual(message.intent.business_domain, "medical")
        self.assertEqual(message.intent.business_type, "medical.resource")
        self.assertEqual(message.intent.business_reference_type, "medication_plan")
        self.assertEqual(message.intent.business_id, "1")
        self.assertIsNotNone(message.recipient_message_id)

    def test_email_otp_creates_outbox_without_plain_code(self):
        ok, reason, message_id = NotificationCenterService.send_email_otp(
            email="demo@example.com",
            code="123456",
            request_id="email-otp",
            otp_id="otp-email-1",
            scene="login",
            expires_at=None,
        )

        self.assertTrue(ok, reason)
        message = NotificationMessage.objects.select_related("intent").get(id=int(message_id))
        self.assertEqual(message.channel, NotificationMessage.Channel.EMAIL)
        self.assertEqual(message.status, NotificationMessage.Status.QUEUED)
        self.assertEqual(message.body, "")
        self.assertNotIn("123456", str(message.payload))
        self.assertEqual(message.intent.business_scene, "account.auth.login_otp_requested")
        self.assertTrue(NotificationOutbox.objects.filter(event_type="notification.email_otp.dispatch", aggregate_id=str(message.intent_id)).exists())
