from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import EmailOTP, PhoneOTP, SocialIdentity
from accounts.services.account_identity_service import AccountIdentityService
from accounts.services.login_service import LoginService
from accounts.services.otp_service import OTPService
from common.exceptions import APIError


HEALTH_BUNDLE = "cn.Zhaodk.Health"
MEDICINE_BOX_BUNDLE = "cn.Zhaodk.MedicineBox"
SHARED_SCOPE = "cn.Zhaodk.Health"

IDENTITY_SCOPE_ALIASES = {
    HEALTH_BUNDLE: SHARED_SCOPE,
    MEDICINE_BOX_BUNDLE: SHARED_SCOPE,
}


@override_settings(
    ACCOUNT_IDENTITY_SCOPE_ALIASES=IDENTITY_SCOPE_ALIASES,
    OTP_WHITELIST_PHONES=["+8615385056020", "+8613900139000"],
    OTP_FIXED_WHITELIST_CODE="989898",
    ALIYUN_SMS_OTP_TEMPLATE_CODE="",
)
class AccountIdentityLinkingTests(TestCase):
    phone = "+8615385056020"
    new_phone = "+8613900139000"

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="identity-user", email="", password="unused")
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        SocialIdentity.objects.create(
            user=self.user,
            bundle_id=SHARED_SCOPE,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple-sub-main",
        )
        self.client = APIClient()
        tokens = LoginService._issue_tokens(
            self.user,
            bundle_id=HEALTH_BUNDLE,
            device_id="device-identity",
            request_id="req-setup",
        )
        self.access = tokens["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def _create_email_otp(self, *, email: str, code: str = "989898") -> EmailOTP:
        return EmailOTP.objects.create(
            otp_id=f"email-otp-{email}",
            email=email,
            code_hash=OTPService._hash_code(code),
            expires_at=timezone.now() + timedelta(minutes=5),
            bundle_id=HEALTH_BUNDLE,
            device_id="device-identity",
        )

    def _create_phone_otp(self, *, phone: str, code: str = "989898") -> PhoneOTP:
        return PhoneOTP.objects.create(
            otp_id=f"phone-otp-{phone}",
            phone_number=phone,
            code_hash=OTPService._hash_code(code),
            expires_at=timezone.now() + timedelta(minutes=5),
            bundle_id=HEALTH_BUNDLE,
            device_id="device-identity",
            send_status=PhoneOTP.SendStatus.ACCEPTED,
        )

    def _issue_ticket(self, *, purpose: str = "bind_identity") -> str:
        with patch(
            "accounts.services.account_identity_service.AppleIdentityService.verify_identity_token"
        ) as mock_verify:
            mock_verify.return_value = ({"sub": "apple-sub-main"}, HEALTH_BUNDLE)
            result = AccountIdentityService.verify_and_issue_ticket(
                user=self.user,
                provider="apple",
                purpose=purpose,
                bundle_id=HEALTH_BUNDLE,
                device_id="device-identity",
                request_id="req-ticket",
                identity_token="fake-apple-token",
            )
        return result["verification_ticket"]

    def test_list_identities_returns_three_providers(self):
        response = self.client.get("/api/v1/accounts/identities/", {"bundle_id": HEALTH_BUNDLE})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["identity_scope"], SHARED_SCOPE)
        providers = {item["provider"]: item for item in data["identities"]}
        self.assertTrue(providers["apple"]["bound"])
        self.assertFalse(providers["phone"]["bound"])
        self.assertFalse(providers["email"]["bound"])
        self.assertTrue(providers["phone"]["bindable"])
        self.assertFalse(providers["apple"]["modifiable"])

    def test_bind_email_and_shared_scope_list(self):
        ticket = self._issue_ticket(purpose="bind_identity")
        email = "bind@example.com"
        otp = self._create_email_otp(email=email)

        result = AccountIdentityService.bind_identity(
            user=self.user,
            provider="email",
            verification_ticket=ticket,
            bundle_id=HEALTH_BUNDLE,
            device_id="device-identity",
            request_id="req-bind-email",
            target=email,
            otp_id=otp.otp_id,
            code="989898",
        )
        email_row = next(item for item in result["identities"] if item["provider"] == "email")
        self.assertTrue(email_row["bound"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, email)

        medicine_list = AccountIdentityService.list_identities(
            user=self.user,
            bundle_id=MEDICINE_BOX_BUNDLE,
        )
        medicine_email = next(item for item in medicine_list["identities"] if item["provider"] == "email")
        self.assertTrue(medicine_email["bound"])
        self.assertEqual(medicine_list["identity_scope"], SHARED_SCOPE)
        self.assertEqual(
            SocialIdentity.objects.filter(
                provider=SocialIdentity.Provider.EMAIL,
                provider_uid=email,
            ).count(),
            1,
        )

    def test_bind_conflict_active_user(self):
        User = get_user_model()
        other = User.objects.create_user(username="other", email="other@example.com", password="unused")
        SocialIdentity.objects.create(
            user=other,
            bundle_id=SHARED_SCOPE,
            provider=SocialIdentity.Provider.EMAIL,
            provider_uid="taken@example.com",
        )
        ticket = self._issue_ticket(purpose="bind_identity")
        otp = self._create_email_otp(email="taken@example.com")
        with self.assertRaises(APIError) as ctx:
            AccountIdentityService.bind_identity(
                user=self.user,
                provider="email",
                verification_ticket=ticket,
                bundle_id=HEALTH_BUNDLE,
                device_id="device-identity",
                request_id="req-conflict",
                target="taken@example.com",
                otp_id=otp.otp_id,
                code="989898",
            )
        self.assertEqual(ctx.exception.msg, "identity_already_bound_to_active_user")
        self.assertEqual(ctx.exception.code, 40921)

    def test_bind_inactive_user_allows_rebind(self):
        User = get_user_model()
        inactive = User.objects.create_user(username="inactive", email="old@example.com", password="unused")
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])
        SocialIdentity.objects.create(
            user=inactive,
            bundle_id=SHARED_SCOPE,
            provider=SocialIdentity.Provider.EMAIL,
            provider_uid="old@example.com",
        )
        ticket = self._issue_ticket(purpose="bind_identity")
        otp = self._create_email_otp(email="old@example.com")
        result = AccountIdentityService.bind_identity(
            user=self.user,
            provider="email",
            verification_ticket=ticket,
            bundle_id=HEALTH_BUNDLE,
            device_id="device-identity",
            request_id="req-rebind",
            target="old@example.com",
            otp_id=otp.otp_id,
            code="989898",
        )
        email_row = next(item for item in result["identities"] if item["provider"] == "email")
        self.assertTrue(email_row["bound"])
        identity = SocialIdentity.objects.get(
            bundle_id=SHARED_SCOPE,
            provider=SocialIdentity.Provider.EMAIL,
            provider_uid="old@example.com",
        )
        self.assertEqual(identity.user_id, self.user.id)

    def test_ticket_cannot_be_reused(self):
        ticket = self._issue_ticket(purpose="bind_identity")
        email = "once@example.com"
        otp = self._create_email_otp(email=email)
        AccountIdentityService.bind_identity(
            user=self.user,
            provider="email",
            verification_ticket=ticket,
            bundle_id=HEALTH_BUNDLE,
            device_id="device-identity",
            request_id="req-once",
            target=email,
            otp_id=otp.otp_id,
            code="989898",
        )
        otp2 = self._create_email_otp(email="twice@example.com")
        EmailOTP.objects.filter(id=otp2.id).update(otp_id="email-otp-twice@example.com")
        with self.assertRaises(APIError) as ctx:
            AccountIdentityService.bind_identity(
                user=self.user,
                provider="email",
                verification_ticket=ticket,
                bundle_id=HEALTH_BUNDLE,
                device_id="device-identity",
                request_id="req-reuse",
                target="twice@example.com",
                otp_id="email-otp-twice@example.com",
                code="989898",
            )
        self.assertEqual(ctx.exception.msg, "verification_ticket_used")

    def test_change_phone(self):
        SocialIdentity.objects.create(
            user=self.user,
            bundle_id=SHARED_SCOPE,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid=self.phone,
        )
        ticket = self._issue_ticket(purpose="change_identity")
        otp = self._create_phone_otp(phone=self.new_phone)
        result = AccountIdentityService.change_identity(
            user=self.user,
            provider="phone",
            verification_ticket=ticket,
            bundle_id=HEALTH_BUNDLE,
            device_id="device-identity",
            request_id="req-change-phone",
            new_target=self.new_phone,
            new_otp_id=otp.otp_id,
            new_code="989898",
        )
        phone_row = next(item for item in result["identities"] if item["provider"] == "phone")
        self.assertTrue(phone_row["bound"])
        self.assertTrue(phone_row["masked_value"].endswith("9000"))
        self.assertEqual(
            SocialIdentity.objects.get(
                user=self.user,
                provider=SocialIdentity.Provider.PHONE,
                bundle_id=SHARED_SCOPE,
            ).provider_uid,
            self.new_phone,
        )

    def test_apple_change_not_supported(self):
        ticket = self._issue_ticket(purpose="change_identity")
        with self.assertRaises(APIError) as ctx:
            AccountIdentityService.change_identity(
                user=self.user,
                provider="apple",
                verification_ticket=ticket,
                bundle_id=HEALTH_BUNDLE,
                device_id="device-identity",
                request_id="req-apple-change",
            )
        self.assertEqual(ctx.exception.msg, "apple_identity_change_not_supported")

    def test_bind_api_endpoint(self):
        ticket = self._issue_ticket(purpose="bind_identity")
        email = "api-bind@example.com"
        otp = self._create_email_otp(email=email)
        response = self.client.post(
            "/api/v1/accounts/identities/bind/",
            {
                "provider": "email",
                "target": email,
                "otp_id": otp.otp_id,
                "code": "989898",
                "verification_ticket": ticket,
                "bundle_id": HEALTH_BUNDLE,
                "device_id": "device-identity",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["msg"], "bound")
        providers = {item["provider"]: item for item in response.json()["data"]["identities"]}
        self.assertTrue(providers["email"]["bound"])


@override_settings(APPLE_ALLOWED_BUNDLE_IDS=["com.sparkclient.ios"])
class AppleEmailOverwriteProtectionTests(TestCase):
    bundle_id = "com.sparkclient.ios"
    device_id = "device-apple-email-guard"

    def test_existing_email_not_overwritten(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="apple_email_guard",
            email="old@example.com",
            password="unused",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        SocialIdentity.objects.create(
            user=user,
            bundle_id=self.bundle_id,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple-sub-email-guard",
        )
        with patch("accounts.services.login_service.AppleIdentityService.verify_identity_token") as mock_verify:
            mock_verify.return_value = (
                {
                    "sub": "apple-sub-email-guard",
                    "email": "new@example.com",
                    "email_verified": True,
                },
                self.bundle_id,
            )
            result = LoginService.authenticate_apple_and_issue_tokens(
                identity_token="fake-token",
                bundle_id=self.bundle_id,
                nonce="",
                user_identifier="apple-user",
                email="new@example.com",
                full_name="",
                ip_address="127.0.0.1",
                user_agent="unit-test",
                device_id=self.device_id,
                request_id="req-email-guard",
            )
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")
        self.assertEqual(result["email"], "old@example.com")
        self.assertFalse(
            SocialIdentity.objects.filter(
                user=user,
                provider=SocialIdentity.Provider.EMAIL,
            ).exists()
        )

    def test_empty_email_backfilled_when_verified(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="apple_email_empty",
            email="",
            password="unused",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        SocialIdentity.objects.create(
            user=user,
            bundle_id=self.bundle_id,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple-sub-email-empty",
        )
        with patch("accounts.services.login_service.AppleIdentityService.verify_identity_token") as mock_verify:
            mock_verify.return_value = (
                {
                    "sub": "apple-sub-email-empty",
                    "email": "fill@example.com",
                    "email_verified": True,
                },
                self.bundle_id,
            )
            result = LoginService.authenticate_apple_and_issue_tokens(
                identity_token="fake-token",
                bundle_id=self.bundle_id,
                nonce="",
                user_identifier="apple-user",
                email="fill@example.com",
                full_name="",
                ip_address="127.0.0.1",
                user_agent="unit-test",
                device_id=self.device_id,
                request_id="req-email-fill",
            )
        user.refresh_from_db()
        self.assertEqual(user.email, "fill@example.com")
        self.assertEqual(result["email"], "fill@example.com")
        self.assertFalse(
            SocialIdentity.objects.filter(
                user=user,
                provider=SocialIdentity.Provider.EMAIL,
            ).exists()
        )


@override_settings(
    ACCOUNT_IDENTITY_SCOPE_ALIASES=IDENTITY_SCOPE_ALIASES,
)
class EmailOTPSocialIdentityLoginTests(TestCase):
    def test_email_otp_login_creates_email_social_identity(self):
        email = "login-email@example.com"
        EmailOTP.objects.create(
            otp_id="email-login-1",
            email=email,
            code_hash=OTPService._hash_code("123456"),
            expires_at=timezone.now() + timedelta(minutes=5),
            bundle_id=HEALTH_BUNDLE,
            device_id="device-email-login",
        )
        result = OTPService.verify_email_otp_and_issue_tokens(
            otp_id="email-login-1",
            email=email,
            code="123456",
            request_id="req-email-login",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id=HEALTH_BUNDLE,
            device_id="device-email-login",
        )
        self.assertTrue(result["is_new_user"])
        identity = SocialIdentity.objects.get(
            provider=SocialIdentity.Provider.EMAIL,
            provider_uid=email,
        )
        self.assertEqual(identity.bundle_id, SHARED_SCOPE)
        self.assertEqual(identity.user_id, result["user_id"])

    def test_medicine_box_hits_same_email_identity(self):
        email = "shared-email@example.com"
        EmailOTP.objects.create(
            otp_id="email-shared-1",
            email=email,
            code_hash=OTPService._hash_code("123456"),
            expires_at=timezone.now() + timedelta(minutes=5),
            bundle_id=HEALTH_BUNDLE,
            device_id="device-a",
        )
        first = OTPService.verify_email_otp_and_issue_tokens(
            otp_id="email-shared-1",
            email=email,
            code="123456",
            request_id="req-email-shared-1",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id=HEALTH_BUNDLE,
            device_id="device-a",
        )
        EmailOTP.objects.create(
            otp_id="email-shared-2",
            email=email,
            code_hash=OTPService._hash_code("123456"),
            expires_at=timezone.now() + timedelta(minutes=5),
            bundle_id=MEDICINE_BOX_BUNDLE,
            device_id="device-b",
        )
        second = OTPService.verify_email_otp_and_issue_tokens(
            otp_id="email-shared-2",
            email=email,
            code="123456",
            request_id="req-email-shared-2",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id=MEDICINE_BOX_BUNDLE,
            device_id="device-b",
        )
        self.assertEqual(first["user_id"], second["user_id"])
        self.assertFalse(second["is_new_user"])
        self.assertEqual(
            SocialIdentity.objects.filter(
                provider=SocialIdentity.Provider.EMAIL,
                provider_uid=email,
            ).count(),
            1,
        )
