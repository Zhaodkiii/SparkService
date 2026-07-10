from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.models import LoginAudit, SocialIdentity
from accounts.services.login_service import LoginService


@override_settings(APPLE_ALLOWED_BUNDLE_IDS=["com.sparkclient.ios"])
class AppleDisplayNameTests(TestCase):
    bundle_id = "com.sparkclient.ios"
    device_id = "device-apple-display-name"

    def _apple_login(self, *, subject: str, email: str, full_name: str, request_id: str):
        with patch("accounts.services.login_service.AppleIdentityService.verify_identity_token") as mock_verify:
            mock_verify.return_value = ({"sub": subject, "email": email}, self.bundle_id)
            return LoginService.authenticate_apple_and_issue_tokens(
                identity_token="fake-token",
                bundle_id=self.bundle_id,
                nonce="",
                user_identifier=f"apple-{subject}",
                email=email,
                full_name=full_name,
                ip_address="127.0.0.1",
                user_agent="unit-test",
                device_id=self.device_id,
                request_id=request_id,
            )

    def test_first_login_persists_full_name_to_first_name(self):
        result = self._apple_login(
            subject="apple-sub-name-1",
            email="apple-name@example.com",
            full_name="哈哈哈哈 Dream",
            request_id="req-apple-name-1",
        )

        User = get_user_model()
        user = User.objects.get(id=result["user_id"])
        self.assertEqual(user.first_name, "哈哈哈哈 Dream")
        self.assertTrue(user.username.startswith("apple_"))
        self.assertNotEqual(user.username, "哈哈哈哈 Dream")
        self.assertEqual(result["display_name"], "哈哈哈哈 Dream")
        self.assertTrue(result["is_new_user"])

        audit = LoginAudit.objects.filter(user=user, request_id="req-apple-name-1").first()
        self.assertIsNotNone(audit)
        self.assertTrue(audit.raw_claims["client_full_name_present"])
        self.assertEqual(audit.raw_claims["client_full_name"], "哈哈哈哈 Dream")

    def test_first_login_without_full_name_leaves_first_name_empty(self):
        result = self._apple_login(
            subject="apple-sub-no-name",
            email="no-name@example.com",
            full_name="",
            request_id="req-apple-no-name",
        )

        User = get_user_model()
        user = User.objects.get(id=result["user_id"])
        self.assertEqual(user.first_name, "")
        self.assertEqual(result["display_name"], "no-name")

        audit = LoginAudit.objects.filter(user=user, request_id="req-apple-no-name").first()
        self.assertFalse(audit.raw_claims["client_full_name_present"])

    def test_existing_user_backfills_empty_first_name(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="apple_apple-sub-backfill",
            email="backfill@example.com",
            password="unused",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        SocialIdentity.objects.create(
            user=user,
            bundle_id=self.bundle_id,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple-sub-backfill",
        )

        result = self._apple_login(
            subject="apple-sub-backfill",
            email="backfill@example.com",
            full_name="补全名称",
            request_id="req-apple-backfill",
        )

        user.refresh_from_db()
        self.assertEqual(user.first_name, "补全名称")
        self.assertEqual(result["display_name"], "补全名称")
        self.assertFalse(result["is_new_user"])

    def test_existing_user_does_not_overwrite_first_name_with_empty_full_name(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="apple_apple-sub-keep",
            email="keep@example.com",
            password="unused",
            first_name="已有昵称",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        SocialIdentity.objects.create(
            user=user,
            bundle_id=self.bundle_id,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple-sub-keep",
        )

        result = self._apple_login(
            subject="apple-sub-keep",
            email="keep@example.com",
            full_name="",
            request_id="req-apple-keep",
        )

        user.refresh_from_db()
        self.assertEqual(user.first_name, "已有昵称")
        self.assertEqual(result["display_name"], "已有昵称")
