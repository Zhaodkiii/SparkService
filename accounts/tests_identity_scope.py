from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import AccountDeviceSession, LoginAudit, PhoneOTP, SocialIdentity, TrustedDevice
from accounts.services.identity_scope_service import IdentityScopeService
from accounts.services.login_service import LoginService
from accounts.services.otp_service import OTPService


HEALTH_BUNDLE = "cn.Zhaodk.Health"
MEDICINE_BOX_BUNDLE = "cn.Zhaodk.MedicineBox"
WEB_BUNDLE = "cn.Zhaodk.Health.web"
OTHER_BUNDLE = "cn.zdk.SupportClient"
SHARED_SCOPE = "cn.Zhaodk.Health"

IDENTITY_SCOPE_ALIASES = {
    HEALTH_BUNDLE: SHARED_SCOPE,
    MEDICINE_BOX_BUNDLE: SHARED_SCOPE,
    WEB_BUNDLE: SHARED_SCOPE,
}


@override_settings(ACCOUNT_IDENTITY_SCOPE_ALIASES=IDENTITY_SCOPE_ALIASES)
class IdentityScopeServiceTests(TestCase):
    def test_resolve_health_returns_itself(self):
        self.assertEqual(IdentityScopeService.resolve(HEALTH_BUNDLE), SHARED_SCOPE)

    def test_resolve_medicine_box_maps_to_health(self):
        self.assertEqual(IdentityScopeService.resolve(MEDICINE_BOX_BUNDLE), SHARED_SCOPE)

    def test_resolve_web_maps_to_health(self):
        self.assertEqual(IdentityScopeService.resolve(WEB_BUNDLE), SHARED_SCOPE)

    def test_resolve_unconfigured_bundle_returns_itself(self):
        self.assertEqual(IdentityScopeService.resolve(OTHER_BUNDLE), OTHER_BUNDLE)

    def test_resolve_blank_returns_empty(self):
        self.assertEqual(IdentityScopeService.resolve(""), "")
        self.assertEqual(IdentityScopeService.resolve("   "), "")


@override_settings(
    ACCOUNT_IDENTITY_SCOPE_ALIASES=IDENTITY_SCOPE_ALIASES,
    OTP_WHITELIST_PHONES=["+8615385056020"],
    OTP_FIXED_WHITELIST_CODE="989898",
    ALIYUN_SMS_OTP_TEMPLATE_CODE="",
)
class SharedPhoneIdentityScopeTests(TestCase):
    phone = "+8615385056020"

    def _login(self, *, bundle_id: str, device_id: str, request_id: str) -> dict:
        requested = OTPService.request_phone_otp(
            phone_number=self.phone,
            provider_uid="",
            bundle_id=bundle_id,
            device_id=device_id,
            ip_address="127.0.0.1",
            request_id=request_id,
        )
        return OTPService.verify_phone_otp_and_issue_tokens(
            otp_id=requested["otp_id"],
            phone_number=self.phone,
            code="989898",
            request_id=request_id,
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id=bundle_id,
            device_id=device_id,
        )

    def test_health_then_medicine_box_hit_same_user(self):
        health = self._login(
            bundle_id=HEALTH_BUNDLE,
            device_id="device-health",
            request_id="req-health-phone",
        )
        medicine = self._login(
            bundle_id=MEDICINE_BOX_BUNDLE,
            device_id="device-medicine",
            request_id="req-medicine-phone",
        )

        self.assertTrue(health["is_new_user"])
        self.assertFalse(medicine["is_new_user"])
        self.assertEqual(health["user_id"], medicine["user_id"])

        identities = SocialIdentity.objects.filter(
            provider=SocialIdentity.Provider.PHONE,
            provider_uid=self.phone,
        )
        self.assertEqual(identities.count(), 1)
        identity = identities.get()
        self.assertEqual(identity.bundle_id, SHARED_SCOPE)
        self.assertEqual(identity.user_id, health["user_id"])
        self.assertFalse(
            SocialIdentity.objects.filter(
                bundle_id=MEDICINE_BOX_BUNDLE,
                provider=SocialIdentity.Provider.PHONE,
                provider_uid=self.phone,
            ).exists()
        )

        otp = PhoneOTP.objects.get(request_id="req-medicine-phone")
        self.assertEqual(otp.bundle_id, MEDICINE_BOX_BUNDLE)

        audit = LoginAudit.objects.get(request_id="req-medicine-phone")
        self.assertEqual(audit.bundle_id, MEDICINE_BOX_BUNDLE)
        self.assertEqual(audit.user_id, health["user_id"])

        device = TrustedDevice.objects.get(bundle_id=MEDICINE_BOX_BUNDLE, device_id="device-medicine")
        self.assertEqual(device.user_id, health["user_id"])

        session = AccountDeviceSession.objects.get(
            user_id=health["user_id"],
            device_id="device-medicine",
            status=AccountDeviceSession.Status.ACTIVE,
        )
        self.assertEqual(session.bundle_id, MEDICINE_BOX_BUNDLE)

        token = AccessToken(medicine["access_token"])
        self.assertEqual(token["bundle_id"], MEDICINE_BOX_BUNDLE)

    def test_health_then_web_hit_same_user(self):
        health = self._login(bundle_id=HEALTH_BUNDLE, device_id="device-health-web", request_id="req-health-web")
        web = self._login(bundle_id=WEB_BUNDLE, device_id="device-web", request_id="req-web-phone")
        self.assertEqual(health["user_id"], web["user_id"])
        self.assertEqual(web["identity_scope"], SHARED_SCOPE)
        self.assertEqual(AccessToken(web["access_token"])["bundle_id"], WEB_BUNDLE)

    def test_other_bundle_keeps_isolated_user(self):
        health = self._login(
            bundle_id=HEALTH_BUNDLE,
            device_id="device-health-2",
            request_id="req-health-isolated",
        )
        other = self._login(
            bundle_id=OTHER_BUNDLE,
            device_id="device-other",
            request_id="req-other-isolated",
        )

        self.assertNotEqual(health["user_id"], other["user_id"])
        self.assertEqual(
            SocialIdentity.objects.filter(
                provider=SocialIdentity.Provider.PHONE,
                provider_uid=self.phone,
            ).count(),
            2,
        )
        self.assertTrue(
            SocialIdentity.objects.filter(
                bundle_id=SHARED_SCOPE,
                provider=SocialIdentity.Provider.PHONE,
                provider_uid=self.phone,
                user_id=health["user_id"],
            ).exists()
        )
        self.assertTrue(
            SocialIdentity.objects.filter(
                bundle_id=OTHER_BUNDLE,
                provider=SocialIdentity.Provider.PHONE,
                provider_uid=self.phone,
                user_id=other["user_id"],
            ).exists()
        )

    def test_request_phone_otp_resolves_shared_identity_for_medicine_box(self):
        User = get_user_model()
        user = User.objects.create_user(username="shared-phone-user", password="x")
        SocialIdentity.objects.create(
            user=user,
            bundle_id=SHARED_SCOPE,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid=self.phone,
        )

        result = OTPService.request_phone_otp(
            phone_number=self.phone,
            provider_uid="",
            bundle_id=MEDICINE_BOX_BUNDLE,
            device_id="device-medicine-request",
            ip_address="127.0.0.1",
            request_id="req-medicine-resolve",
            scene="login",
        )

        otp = PhoneOTP.objects.get(otp_id=result["otp_id"])
        self.assertEqual(otp.bundle_id, MEDICINE_BOX_BUNDLE)
        self.assertEqual(otp.requested_user_id, user.id)
        self.assertEqual(otp.resolved_identity.user_id, user.id)


@override_settings(
    ACCOUNT_IDENTITY_SCOPE_ALIASES=IDENTITY_SCOPE_ALIASES,
    APPLE_ALLOWED_BUNDLE_IDS=[HEALTH_BUNDLE, MEDICINE_BOX_BUNDLE, OTHER_BUNDLE],
)
class SharedAppleIdentityScopeTests(TestCase):
    subject = "apple-shared-sub-001"

    def _apple_login(self, *, bundle_id: str, device_id: str, request_id: str) -> dict:
        with patch("accounts.services.login_service.AppleIdentityService.verify_identity_token") as mock_verify:
            mock_verify.return_value = (
                {"sub": self.subject, "email": "shared-apple@example.com", "aud": bundle_id},
                bundle_id,
            )
            result = LoginService.authenticate_apple_and_issue_tokens(
                identity_token="fake-token",
                bundle_id=bundle_id,
                nonce="",
                user_identifier=f"apple-{self.subject}",
                email="shared-apple@example.com",
                full_name="Shared Apple",
                ip_address="127.0.0.1",
                user_agent="unit-test",
                device_id=device_id,
                request_id=request_id,
            )
            mock_verify.assert_called_once()
            self.assertEqual(mock_verify.call_args.kwargs["audiences"], [bundle_id])
            return result

    def test_health_then_medicine_box_hit_same_apple_user(self):
        health = self._apple_login(
            bundle_id=HEALTH_BUNDLE,
            device_id="apple-device-health",
            request_id="req-apple-health",
        )
        medicine = self._apple_login(
            bundle_id=MEDICINE_BOX_BUNDLE,
            device_id="apple-device-medicine",
            request_id="req-apple-medicine",
        )

        self.assertTrue(health["is_new_user"])
        self.assertFalse(medicine["is_new_user"])
        self.assertEqual(health["user_id"], medicine["user_id"])

        identities = SocialIdentity.objects.filter(
            provider=SocialIdentity.Provider.APPLE,
            provider_uid=self.subject,
        )
        self.assertEqual(identities.count(), 1)
        identity = identities.get()
        self.assertEqual(identity.bundle_id, SHARED_SCOPE)
        self.assertFalse(
            SocialIdentity.objects.filter(
                bundle_id=MEDICINE_BOX_BUNDLE,
                provider=SocialIdentity.Provider.APPLE,
                provider_uid=self.subject,
            ).exists()
        )

        audit = LoginAudit.objects.get(request_id="req-apple-medicine")
        self.assertEqual(audit.bundle_id, MEDICINE_BOX_BUNDLE)
        self.assertEqual(audit.user_id, health["user_id"])

        session = AccountDeviceSession.objects.get(
            user_id=health["user_id"],
            device_id="apple-device-medicine",
            status=AccountDeviceSession.Status.ACTIVE,
        )
        self.assertEqual(session.bundle_id, MEDICINE_BOX_BUNDLE)

        token = AccessToken(medicine["access_token"])
        self.assertEqual(token["bundle_id"], MEDICINE_BOX_BUNDLE)

    def test_apple_aud_still_requires_real_request_bundle(self):
        with patch("accounts.services.login_service.AppleIdentityService.verify_identity_token") as mock_verify:
            mock_verify.return_value = (
                {"sub": "apple-aud-check", "email": "aud@example.com"},
                HEALTH_BUNDLE,
            )
            LoginService.authenticate_apple_and_issue_tokens(
                identity_token="fake-token",
                bundle_id=HEALTH_BUNDLE,
                nonce="",
                user_identifier="apple-aud-check",
                email="aud@example.com",
                full_name="",
                ip_address="127.0.0.1",
                user_agent="unit-test",
                device_id="apple-aud-device",
                request_id="req-apple-aud",
            )
            self.assertEqual(mock_verify.call_args.kwargs["audiences"], [HEALTH_BUNDLE])


@override_settings(ACCOUNT_IDENTITY_SCOPE_ALIASES=IDENTITY_SCOPE_ALIASES)
class IdentifierLookupIdentityScopeTests(TestCase):
    def test_find_user_by_phone_uses_identity_scope(self):
        User = get_user_model()
        user = User.objects.create_user(username="id-lookup-user", password="x")
        SocialIdentity.objects.create(
            user=user,
            bundle_id=SHARED_SCOPE,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8615385056020",
        )

        found = LoginService._find_user_by_identifier("+8615385056020", bundle_id=MEDICINE_BOX_BUNDLE)
        self.assertEqual(found.id, user.id)

        missing = LoginService._find_user_by_identifier("+8615385056020", bundle_id=OTHER_BUNDLE)
        self.assertIsNone(missing)
