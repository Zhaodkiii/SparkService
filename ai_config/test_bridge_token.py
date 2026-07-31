from datetime import datetime, timedelta, timezone

import jwt
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase


@override_settings(
    AI_CHAT_ALLOWED_BUNDLES=["cn.zhaodk.SupportClient"],
    AI_CHAT_BRIDGE_TOKEN_TTL_MINUTES=10,
    DEEPTUTOR_HTTP_BASE_URL="http://192.168.1.152:9898",
    DEEPTUTOR_WS_URL="ws://192.168.1.152:9898/api/v1/ws",
    DEEPTUTOR_BRIDGE_JWT_SECRET="test-bridge-secret",
)
class AIChatBridgeTokenViewTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="bridge-user",
            email="bridge@example.com",
            password="secret123",
        )

    def _request_body(self, **overrides):
        body = {
            "client": "ios",
            "device_id": "debug-device",
            "app_bundle": "cn.zhaodk.SupportClient",
            "purpose": "deeptutor_ai_chat",
        }
        body.update(overrides)
        return body

    def test_unauthenticated_request_returns_401(self):
        response = self.client.post("/api/v1/ai/chat/token/", self._request_body(), format="json")
        self.assertEqual(response.status_code, 401)

    def test_invalid_purpose_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/v1/ai/chat/token/",
            self._request_body(purpose="other"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], 40001)

    def test_forbidden_bundle_returns_403(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/v1/ai/chat/token/",
            self._request_body(app_bundle="com.example.other"),
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], 40301)

    def test_valid_request_returns_bridge_token(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/v1/ai/chat/token/", self._request_body(), format="json")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["msg"], "ok")
        self.assertIn("token", payload["data"])
        self.assertIn("expires_at", payload["data"])
        self.assertEqual(payload["data"]["deeptutor_ws_url"], "ws://192.168.1.152:9898/api/v1/ws")
        self.assertEqual(payload["data"]["deeptutor_http_base_url"], "http://192.168.1.152:9898")

        decoded = jwt.decode(
            payload["data"]["token"],
            "test-bridge-secret",
            algorithms=["HS256"],
            audience="DeepTutorSerevr",
            issuer="SparkService",
        )
        self.assertEqual(decoded["token_type"], "deeptutor_bridge")
        self.assertEqual(decoded["purpose"], "deeptutor_ai_chat")
        self.assertEqual(decoded["client"], "ios")
        self.assertEqual(decoded["bundle_id"], "cn.zhaodk.SupportClient")
        self.assertEqual(decoded["user_id"], str(self.user.id))

        expires_at = datetime.fromtimestamp(payload["data"]["expires_at"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        self.assertGreater(expires_at, now)
        self.assertLessEqual(expires_at, now + timedelta(minutes=11))
