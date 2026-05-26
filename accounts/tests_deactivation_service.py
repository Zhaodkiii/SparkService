import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import AccountDeactivation, AccountDeactivationAudit, AccountProfile, EmailOTP, SocialIdentity, TrustedDevice
from accounts.services.deactivation_service import DeactivationService
from accounts.services.otp_service import OTPService

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="spark_deactivation_tests_")


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class DeactivationServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", email="tester@example.com", password="secret123", first_name="Test")
        self.profile = AccountProfile.objects.create(user=self.user)
        SocialIdentity.objects.create(user=self.user, provider=SocialIdentity.Provider.APPLE, provider_uid="apple-sub", bundle_id="com.spark")
        SocialIdentity.objects.create(user=self.user, provider=SocialIdentity.Provider.PHONE, provider_uid="+8613800000000", bundle_id="com.spark")
        TrustedDevice.objects.create(user=self.user, bundle_id="com.spark", device_id="device-1", push_token="push", device_name="phone")
        EmailOTP.objects.create(
            otp_id="email-otp",
            email=self.user.email,
            code_hash=OTPService._hash_code("123456"),
            expires_at=timezone.now() + timedelta(minutes=5),
        )

    def test_process_deactivation_runs_full_five_step_flow(self):
        result = DeactivationService.request_deactivation(
            user=self.user,
            request_id="req-1",
            reason="no longer needed",
            immediate_deactivation=True,
            data_retention_days=7,
            anonymize_personal_data=True,
            delete_related_data=True,
        )

        processed = DeactivationService.process_deactivation(deactivation_id=result["deactivation_id"], request_id="req-1")
        row = AccountDeactivation.objects.get(id=result["deactivation_id"])
        self.user.refresh_from_db()

        self.assertEqual(processed["state"], AccountDeactivation.DeactivationState.COMPLETED)
        self.assertEqual(row.state, AccountDeactivation.DeactivationState.COMPLETED)
        self.assertFalse(self.user.is_active)
        self.assertTrue(row.backup_uri)
        self.assertTrue(row.backup_checksum)
        self.assertFalse(SocialIdentity.objects.filter(user=self.user).exists())
        self.assertFalse(AccountProfile.objects.filter(user=self.user).exists())
        self.assertFalse(EmailOTP.objects.filter(email="tester@example.com").exists())

        actions = list(AccountDeactivationAudit.objects.filter(deactivation=row).order_by("id").values_list("action", flat=True))
        self.assertEqual(
            actions,
            [
                AccountDeactivationAudit.AuditAction.REQUESTED,
                AccountDeactivationAudit.AuditAction.DATA_BACKUP,
                AccountDeactivationAudit.AuditAction.DATA_ANONYMIZE,
                AccountDeactivationAudit.AuditAction.RELATED_DATA_DELETE,
                AccountDeactivationAudit.AuditAction.ACCOUNT_DEACTIVATE,
                AccountDeactivationAudit.AuditAction.COMPLETED,
            ],
        )

    def test_process_deactivation_does_not_run_before_scheduled_at(self):
        result = DeactivationService.request_deactivation(
            user=self.user,
            request_id="req-2",
            immediate_deactivation=False,
            countdown_hours=24,
        )

        processed = DeactivationService.process_deactivation(deactivation_id=result["deactivation_id"], request_id="req-2")
        row = AccountDeactivation.objects.get(id=result["deactivation_id"])

        self.assertTrue(processed["noop"])
        self.assertEqual(row.state, AccountDeactivation.DeactivationState.SCHEDULED)
        self.assertFalse(row.backup_uri)

    def test_login_can_cancel_pending_deactivation(self):
        result = DeactivationService.request_deactivation(
            user=self.user,
            request_id="req-3",
            immediate_deactivation=False,
            countdown_hours=24,
        )

        cancelled = DeactivationService.cancel_pending_on_login(user=self.user, request_id="req-3")
        row = AccountDeactivation.objects.get(id=result["deactivation_id"])

        self.assertTrue(cancelled["cancelled"])
        self.assertEqual(row.state, AccountDeactivation.DeactivationState.CANCELLED)
