"""Web Apple login + AccountWebSession tests (CHAT-WEB-019).

Covers the isolation matrix from the ticket:
- Web login creates AccountWebSession only (no TrustedDevice / AccountDeviceSession).
- Web refresh/logout do not touch device sessions; mobile login does not touch web sessions.
- Web and mobile sessions can coexist for the same User.
- Token claim dispatch: web claims -> web domain; both claims -> reject.
"""

import hashlib
import time
from unittest.mock import patch

import jwt as pyjwt
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.auth.web_tokens import SparkWebRefreshToken
from accounts.models import AccountDeviceSession, AccountWebSession, LoginAudit, SocialIdentity, TrustedDevice
from accounts.services.device_session_service import DeviceSessionService
from accounts.services.web_session_service import WebSessionService
from chat_sync.ai_models import ChatWebSocketTicket
from chat_sync.models import ChatThread

User = get_user_model()

WEB_SERVICE_ID = "cn.Zhaodk.Health.web"
IDENTITY_SCOPE = "cn.Zhaodk.Health"


def _make_id_token(*, subject: str, nonce: str, audience: str, email: str = "") -> str:
    import hashlib

    now = int(time.time())
    payload = {
        "iss": "https://appleid.apple.com",
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + 600,
        "nonce": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
    }
    if email:
        payload["email"] = email
        payload["email_verified"] = "true"
    return pyjwt.encode(payload, "test-web-secret", algorithm="HS256")


@override_settings(
    WEB_APPLE_LOGIN_V2_ENABLED=True,
    WEB_SESSION_DOMAIN_ENABLED=True,
    APPLE_WEB_SERVICE_IDS=[WEB_SERVICE_ID],
    APPLE_WEB_ALLOWED_REDIRECT_URIS=["https://chat.example.com/api/auth/apple/callback"],
    ACCOUNT_IDENTITY_SCOPE_ALIASES={WEB_SERVICE_ID: IDENTITY_SCOPE},
)
class WebAppleLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _login(self, *, subject="web-sub-1", nonce="nonce-1", email="web@example.com", code="", redirect_uri="https://chat.example.com/api/auth/apple/callback"):
        identity_token = _make_id_token(subject=subject, nonce=nonce, audience=WEB_SERVICE_ID, email=email)
        with patch(
            "accounts.services.web_apple_identity_service.WebAppleIdentityService._resolve_jwk"
        ) as mock_jwk:
            from rest_framework_simplejwt.tokens import RefreshToken  # noqa: F401  (import side effects)

            public_key = pyjwt.algorithms.HMACAlgorithm("HS256").prepare_key("test-web-secret")
            mock_jwk.return_value = ({"kty": "oct", "k": "dGVzdC13ZWItc2VjcmV0"}, "HS256")
            # jwt.decode with an HMAC key built from the same secret: emulate RSA verify.
            with patch("jwt.algorithms.RSAAlgorithm.from_jwk", return_value=public_key):
                from accounts.services.web_apple_login_service import WebAppleLoginService

                return WebAppleLoginService.authenticate_apple_web_and_issue_tokens(
                    identity_token=identity_token,
                    authorization_code=code,
                    nonce=nonce,
                    service_id=WEB_SERVICE_ID,
                    redirect_uri=redirect_uri,
                    ip_address="127.0.0.1",
                    user_agent="unit-test",
                    request_id="req-web-1",
                    email=email,
                )

    def test_web_login_creates_web_session_and_no_device_records(self):
        result = self._login()

        user = User.objects.get(id=result["user_id"])
        self.assertTrue(result["is_new_user"])
        self.assertEqual(result["session_class"], "web")

        self.assertEqual(AccountWebSession.objects.filter(user=user).count(), 1)
        # 隔离断言：Web 登录不得创建任何移动端会话/设备记录。
        self.assertEqual(AccountDeviceSession.objects.filter(user=user).count(), 0)
        self.assertEqual(TrustedDevice.objects.count(), 0)

        session = AccountWebSession.objects.get(user=user)
        self.assertEqual(session.status, AccountWebSession.Status.ACTIVE)
        self.assertTrue(session.refresh_jti_hash)
        self.assertNotEqual(session.refresh_jti_hash, "")  # 存哈希而非原始 jti

        identity = SocialIdentity.objects.get(
            bundle_id=IDENTITY_SCOPE, provider=SocialIdentity.Provider.APPLE, provider_uid="web-sub-1"
        )
        self.assertEqual(identity.user, user)

        audit = LoginAudit.objects.filter(user=user, request_id="req-web-1").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.bundle_id, WEB_SERVICE_ID)
        self.assertEqual(audit.raw_claims["channel"], "web")

    def test_web_login_token_claims_carry_web_session_only(self):
        result = self._login()
        refresh = pyjwt.decode(result["refresh_token"], options={"verify_signature": False})
        self.assertEqual(refresh["session_class"], "web")
        self.assertIn("web_session_id", refresh)
        self.assertIn("web_session_version", refresh)
        self.assertNotIn("device_session_id", refresh)
        self.assertNotIn("device_id", refresh)
        self.assertNotIn("bundle_id", refresh)

    def test_same_subject_maps_to_same_user_across_domains(self):
        # 移动端先登录（走既有链路，创建设备会话）。
        mobile_user = User.objects.create_user(username="mobile_user", email="mobile@example.com")
        mobile_user.set_unusable_password()
        mobile_user.save(update_fields=["password"])
        SocialIdentity.objects.create(
            user=mobile_user,
            bundle_id=IDENTITY_SCOPE,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="shared-sub",
        )
        trusted = TrustedDevice.objects.create(user=mobile_user, bundle_id="cn.Zhaodk.Health", device_id="dev-1")
        DeviceSessionService.activate_session_on_login(
            user=mobile_user, bundle_id="cn.Zhaodk.Health", device_id="dev-1", request_id="req-mobile"
        )

        # 同一 subject 走 Web 登录：命中同一身份作用域 → 同一 User。
        web_result = self._login(subject="shared-sub", email="shared@example.com")
        self.assertEqual(web_result["user_id"], mobile_user.id)
        self.assertFalse(web_result["is_new_user"])

        # 移动会话保持 ACTIVE，未被 Web 登录替换。
        mobile_session = AccountDeviceSession.objects.get(trusted_device=trusted)
        self.assertEqual(mobile_session.status, AccountDeviceSession.Status.ACTIVE)
        # Web 会话并存。
        self.assertEqual(AccountWebSession.objects.filter(user=mobile_user, status=AccountWebSession.Status.ACTIVE).count(), 1)

    def test_new_subject_with_existing_email_requires_link(self):
        User.objects.create_user(username="email_owner", email="claimed@example.com", password="x")
        with self.assertRaises(Exception) as ctx:
            self._login(subject="other-sub", nonce="nonce-2", email="claimed@example.com")
        self.assertIn("apple_web_identity_link_required", str(getattr(ctx.exception, "msg", ctx.exception)))

    def test_rejected_mobile_fields_in_serializer(self):
        from accounts.auth.serializers import WebAppleLoginSerializer

        serializer = WebAppleLoginSerializer(
            data={
                "identity_token": "t",
                "nonce": "n",
                "service_id": WEB_SERVICE_ID,
                "bundle_id": "cn.Zhaodk.Health",
                "device_id": "dev-x",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("bundle_id", serializer.errors)

    def test_disabled_flag_returns_503(self):
        with override_settings(WEB_APPLE_LOGIN_V2_ENABLED=False):
            from accounts.services.web_apple_login_service import WebAppleLoginService
            from common.exceptions import APIError

            with self.assertRaises(APIError) as ctx:
                WebAppleLoginService.authenticate_apple_web_and_issue_tokens(
                    identity_token="t",
                    authorization_code="",
                    nonce="n",
                    service_id=WEB_SERVICE_ID,
                    redirect_uri="",
                )
            self.assertEqual(ctx.exception.code, 50374)


@override_settings(
    WEB_SESSION_DOMAIN_ENABLED=True,
    ACCOUNT_IDENTITY_SCOPE_ALIASES={WEB_SERVICE_ID: IDENTITY_SCOPE},
)
class WebSessionTests(TestCase):
    def _create_user_with_web_session(self):
        user = User.objects.create_user(username="web_user", email="web-session@example.com")
        user.set_unusable_password()
        user.save(update_fields=["password"])
        session = WebSessionService.create_session(
            user=user, ip_address="127.0.0.1", user_agent="unit-test", request_id="req-ws"
        )
        tokens = WebSessionService.issue_tokens_for_session(user=user, session=session)
        session.refresh_from_db()
        return user, session, tokens

    def test_refresh_rotation_and_replay_rejection(self):
        user, session, tokens = self._create_user_with_web_session()

        refreshed = WebSessionService.validate_refresh_request(refresh_token_str=tokens["refresh_token"])
        new_tokens = WebSessionService.rotate_tokens_after_refresh(user=refreshed[0], session=refreshed[1])
        session.refresh_from_db()
        self.assertEqual(session.session_version, 2)

        # 旧 refresh 重放被拒绝。
        with self.assertRaises(Exception) as ctx:
            WebSessionService.validate_refresh_request(refresh_token_str=tokens["refresh_token"])
        self.assertIn("web_session", str(getattr(ctx.exception, "msg", ctx.exception)))

        # 新 refresh 仍可用。
        again = WebSessionService.validate_refresh_request(refresh_token_str=new_tokens["refresh_token"])
        self.assertEqual(again[1].id, session.id)

    def test_web_logout_revokes_only_current_web_session(self):
        user, session, tokens = self._create_user_with_web_session()
        # 另一个 Web 会话（Web A / Web B 并存）。
        other_session = WebSessionService.create_session(user=user, request_id="req-ws-2")
        WebSessionService.issue_tokens_for_session(user=user, session=other_session)
        # 移动会话并存。
        TrustedDevice.objects.create(user=user, bundle_id="cn.Zhaodk.Health", device_id="dev-2")
        mobile_session = DeviceSessionService.activate_session_on_login(
            user=user, bundle_id="cn.Zhaodk.Health", device_id="dev-2", request_id="req-mobile-2"
        )

        refresh_claims = pyjwt.decode(tokens["refresh_token"], options={"verify_signature": False})
        WebSessionService.logout_current_session(user=user, request_id="req-logout", claims=refresh_claims)

        session.refresh_from_db()
        other_session.refresh_from_db()
        mobile_session.refresh_from_db()
        self.assertEqual(session.status, AccountWebSession.Status.LOGGED_OUT)
        self.assertEqual(other_session.status, AccountWebSession.Status.ACTIVE)
        self.assertEqual(mobile_session.status, AccountDeviceSession.Status.ACTIVE)

    def test_web_refresh_ignores_device_session_lookup(self):
        """Web refresh 不读取或修改移动 Session（隔离矩阵 8.2）。"""
        user, session, tokens = self._create_user_with_web_session()
        TrustedDevice.objects.create(user=user, bundle_id="cn.Zhaodk.Health", device_id="dev-3")
        DeviceSessionService.activate_session_on_login(
            user=user, bundle_id="cn.Zhaodk.Health", device_id="dev-3", request_id="req-mobile-3"
        )

        validated = WebSessionService.validate_refresh_request(refresh_token_str=tokens["refresh_token"])
        self.assertEqual(validated[1].id, session.id)
        # 设备会话仍为 ACTIVE 且未被轮换。
        device = AccountDeviceSession.objects.get(user=user)
        self.assertEqual(device.status, AccountDeviceSession.Status.ACTIVE)

    def test_conflicting_claims_are_rejected(self):
        user, session, tokens = self._create_user_with_web_session()
        refresh = SparkWebRefreshToken.for_web_session(user=user, session=session)
        refresh["device_session_id"] = 12345
        conflict = str(refresh)

        from common.exceptions import APIError

        with self.assertRaises(APIError) as ctx:
            WebSessionService.validate_refresh_request(refresh_token_str=conflict)
        self.assertEqual(ctx.exception.msg, WebSessionService.WEB_SESSION_CLASS_CONFLICT)

        self.assertTrue(
            WebSessionService.claims_conflict_session_classes(
                {"web_session_id": "x", "device_session_id": "y", "session_class": "web"}
            )
        )
        self.assertFalse(
            WebSessionService.claims_conflict_session_classes({"web_session_id": "x", "session_class": "web"})
        )
        self.assertFalse(WebSessionService.claims_conflict_session_classes({"device_session_id": "y"}))

    def test_expired_session_reports_web_specific_error(self):
        user, session, tokens = self._create_user_with_web_session()
        from django.utils import timezone

        AccountWebSession.objects.filter(pk=session.pk).update(
            expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        with self.assertRaises(Exception) as ctx:
            WebSessionService.validate_refresh_request(refresh_token_str=tokens["refresh_token"])
        self.assertEqual(getattr(ctx.exception, "msg", ""), WebSessionService.WEB_SESSION_EXPIRED)

    def test_revoke_all_sessions_for_user(self):
        user, session, tokens = self._create_user_with_web_session()
        WebSessionService.create_session(user=user, request_id="req-ws-3")
        count = WebSessionService.revoke_all_sessions_for_user(user=user, reason="account_deactivated", request_id="req-r")
        self.assertEqual(count, 2)
        self.assertEqual(
            AccountWebSession.objects.filter(user=user, status=AccountWebSession.Status.REVOKED).count(), 2
        )


@override_settings(WEB_SESSION_DOMAIN_ENABLED=True)
class WebSessionApiTests(TestCase):
    """API-level dispatch tests: refresh + logout route by claim."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="api_user", email="api@example.com")
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.session = WebSessionService.create_session(user=self.user, request_id="req-api")
        self.tokens = WebSessionService.issue_tokens_for_session(user=self.user, session=self.session)

    def test_refresh_endpoint_dispatches_web_domain(self):
        response = self.client.post(
            "/api/v1/auth/token/refresh/",
            data={"refresh_token": self.tokens["refresh_token"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json().get("data") or response.json()
        self.assertIn("access_token", data)
        claims = pyjwt.decode(data["refresh_token"], options={"verify_signature": False})
        self.assertEqual(claims["session_class"], "web")
        # 旧 refresh 已失效（版本轮换）。
        old = self.client.post(
            "/api/v1/auth/token/refresh/",
            data={"refresh_token": self.tokens["refresh_token"]},
            format="json",
        )
        self.assertEqual(old.status_code, 401)

    def test_logout_endpoint_revokes_web_session_only(self):
        TrustedDevice.objects.create(user=self.user, bundle_id="cn.Zhaodk.Health", device_id="dev-api")
        mobile = DeviceSessionService.activate_session_on_login(
            user=self.user, bundle_id="cn.Zhaodk.Health", device_id="dev-api", request_id="req-m-api"
        )
        response = self.client.post(
            "/api/v1/auth/logout/",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access_token']}",
        )
        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        mobile.refresh_from_db()
        self.assertEqual(self.session.status, AccountWebSession.Status.LOGGED_OUT)
        self.assertEqual(mobile.status, AccountDeviceSession.Status.ACTIVE)

    def test_session_endpoint_accepts_web_token(self):
        response = self.client.get(
            "/api/v1/auth/session/",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access_token']}",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json().get("data") or response.json()
        self.assertEqual(data.get("user_id"), self.user.id)


@override_settings(WEB_SESSION_DOMAIN_ENABLED=True)
class WebChatSharingTests(TestCase):
    """019F：Web 会话命中同一 User → 共享 Thread/Run；Web logout 不删除对话。"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="chat_user", email="chat@example.com")
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.thread = ChatThread.objects.create(user=self.user, title="shared thread")
        self.session = WebSessionService.create_session(user=self.user, request_id="req-chat")
        self.tokens = WebSessionService.issue_tokens_for_session(user=self.user, session=self.session)

    def test_web_token_creates_ws_ticket_and_reads_thread_data(self):
        response = self.client.post(
            "/api/v1/ai/chat/ws-tickets/",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access_token']}",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json().get("data") or response.json()
        self.assertIn("ticket", data)
        self.assertEqual(data["websocket_path"], "/ws/chat/runs/")
        ticket = ChatWebSocketTicket.objects.get(token_hash=hashlib.sha256(data["ticket"].encode()).hexdigest())
        self.assertEqual(ticket.web_session_id, self.session.id)
        self.assertEqual(ticket.web_session_version, self.session.session_version)

        # Thread 权限沿用 User：Web 与移动端读取同一份对话。
        response = self.client.get(
            f"/api/v1/ai/chat/threads/{self.thread.id}/preferences/",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access_token']}",
        )
        self.assertEqual(response.status_code, 200)

    def test_web_logout_keeps_chat_data(self):
        self.client.post(
            "/api/v1/auth/logout/",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access_token']}",
        )
        self.assertTrue(ChatThread.objects.filter(id=self.thread.id).exists())
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, AccountWebSession.Status.LOGGED_OUT)

    def test_mobile_session_change_does_not_invalidate_web_token(self):
        TrustedDevice.objects.create(user=self.user, bundle_id="cn.Zhaodk.Health", device_id="dev-x")
        DeviceSessionService.activate_session_on_login(
            user=self.user, bundle_id="cn.Zhaodk.Health", device_id="dev-x", request_id="req-mobile-x"
        )
        # 移动端再次登录（新设备）会替换移动会话，但 Web access token 仍然有效。
        TrustedDevice.objects.create(user=self.user, bundle_id="cn.Zhaodk.Health", device_id="dev-y")
        DeviceSessionService.activate_session_on_login(
            user=self.user, bundle_id="cn.Zhaodk.Health", device_id="dev-y", request_id="req-mobile-y"
        )
        response = self.client.post(
            "/api/v1/ai/chat/ws-tickets/",
            HTTP_AUTHORIZATION=f"Bearer {self.tokens['access_token']}",
        )
        self.assertEqual(response.status_code, 201)
