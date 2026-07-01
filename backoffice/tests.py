from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts.models import AccountDeviceSession, TrustedDevice
from backoffice.models import AdminAuditLog, AdminRole, AdminUserRole
from backoffice.rbac import bootstrap_admin_permissions


User = get_user_model()


class BackofficePermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = User.objects.create_user(
            username="staff_user",
            email="staff@example.com",
            password="pass1234",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="normal_user",
            email="normal@example.com",
            password="pass1234",
            is_staff=False,
        )
        self.target_user = User.objects.create_user(
            username="target_user",
            email="target@example.com",
            password="pass1234",
            is_staff=False,
        )

        bootstrap_admin_permissions()
        super_admin = AdminRole.objects.get(code="super_admin")
        AdminUserRole.objects.create(user=self.staff_user, role=super_admin)

    def test_dashboard_allows_staff(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/dashboard/overview/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_blocks_non_staff(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get("/api/admin/v1/dashboard/overview/")
        self.assertEqual(response.status_code, 403)

    def test_admin_login_success(self):
        response = self.client.post(
            "/api/admin/v1/auth/login/",
            {"username": "staff_user", "password": "pass1234"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data["data"])
        access = AccessToken(response.data["data"]["access"])
        refresh = RefreshToken(response.data["data"]["refresh"])
        self.assertEqual(access["exp"] - access["iat"], 24 * 60 * 60)
        self.assertEqual(refresh["exp"] - refresh["iat"], 24 * 60 * 60)

    def test_admin_login_remember_me_30_days(self):
        response = self.client.post(
            "/api/admin/v1/auth/login/",
            {"username": "staff_user", "password": "pass1234", "remember_me": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        access = AccessToken(response.data["data"]["access"])
        refresh = RefreshToken(response.data["data"]["refresh"])
        self.assertEqual(access["exp"] - access["iat"], 30 * 24 * 60 * 60)
        self.assertEqual(refresh["exp"] - refresh["iat"], 30 * 24 * 60 * 60)

    def test_admin_login_remember_me_does_not_bypass_admin_check(self):
        response = self.client.post(
            "/api/admin/v1/auth/login/",
            {"username": "normal_user", "password": "pass1234", "remember_me": True},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_login_remember_me_refresh_within_lifetime(self):
        login_response = self.client.post(
            "/api/admin/v1/auth/login/",
            {"username": "staff_user", "password": "pass1234", "remember_me": True},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)
        refresh_token = login_response.data["data"]["refresh"]

        refresh_response = self.client.post(
            "/api/v1/auth/token/refresh/",
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(refresh_response.status_code, 200)
        payload = refresh_response.data
        access_token = payload.get("access_token") or payload.get("access")
        self.assertTrue(access_token)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        profile_response = self.client.get("/api/admin/v1/auth/profile/")
        self.assertEqual(profile_response.status_code, 200)

    def test_user_status_update_writes_audit(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            f"/api/admin/v1/users/{self.target_user.id}/status/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_active)
        self.assertTrue(AdminAuditLog.objects.filter(action="admin.user.status.update", resource_id=str(self.target_user.id)).exists())

    def test_user_detail_allows_staff(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["user"]["id"], self.target_user.id)
        self.assertEqual(data["trusted_devices"], [])
        self.assertEqual(data["device_sessions"], [])

    def test_user_detail_blocks_non_staff(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 403)

    def test_user_detail_not_found(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/users/999999/detail/")
        self.assertEqual(response.status_code, 404)

    def test_user_detail_with_devices_and_sessions(self):
        device_old = TrustedDevice.objects.create(
            user=self.target_user,
            bundle_id="cn.Zhaodk.Health",
            device_id="device-old",
            push_token="806a03abcdef1234567890abcdef2386b2",
            platform="iOS",
            system_version="26.2",
            device_model="arm64",
            device_model_name="iPhone",
            device_name="Old iPhone",
            country_code="CN",
            region_code="CN",
            language_code="zh",
            is_simulator=False,
            is_revoked=True,
            request_id="req-old",
        )
        device_new = TrustedDevice.objects.create(
            user=self.target_user,
            bundle_id="cn.Zhaodk.Health",
            device_id="device-new",
            push_token="",
            platform="iOS",
            system_version="26.2",
            device_model="arm64",
            device_model_name="iPhone",
            device_name="New iPhone",
            country_code="CN",
            region_code="CN",
            language_code="zh",
            is_simulator=True,
            is_revoked=False,
            request_id="req-new",
        )
        session_revoked = AccountDeviceSession.objects.create(
            user=self.target_user,
            trusted_device=device_old,
            bundle_id=device_old.bundle_id,
            device_id=device_old.device_id,
            session_version=1,
            status=AccountDeviceSession.Status.REVOKED,
            revoked_reason="replaced_by_new_device",
        )
        session_active = AccountDeviceSession.objects.create(
            user=self.target_user,
            trusted_device=device_new,
            bundle_id=device_new.bundle_id,
            device_id=device_new.device_id,
            session_version=2,
            status=AccountDeviceSession.Status.ACTIVE,
            replaced_by=None,
        )
        session_revoked.replaced_by = session_active
        session_revoked.save(update_fields=["replaced_by"])

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]

        self.assertEqual(len(data["trusted_devices"]), 2)
        self.assertEqual(data["trusted_devices"][0]["id"], device_new.id)
        self.assertEqual(data["trusted_devices"][1]["id"], device_old.id)
        self.assertEqual(data["trusted_devices"][1]["push_token_masked"], "806a03...2386b2")
        self.assertNotIn("push_token", data["trusted_devices"][1])
        self.assertTrue(data["trusted_devices"][0]["is_simulator"])
        self.assertTrue(data["trusted_devices"][1]["is_revoked"])

        self.assertEqual(len(data["device_sessions"]), 2)
        self.assertEqual(data["device_sessions"][0]["id"], session_active.id)
        self.assertEqual(data["device_sessions"][0]["status"], "active")
        self.assertEqual(data["device_sessions"][1]["id"], session_revoked.id)
        self.assertEqual(data["device_sessions"][1]["status"], "revoked")
        self.assertEqual(data["device_sessions"][1]["replaced_by"], session_active.id)

    def test_user_list_includes_last_used_at(self):
        from django.utils import timezone

        device_time = timezone.now() - timezone.timedelta(hours=2)
        login_time = timezone.now() - timezone.timedelta(hours=5)
        refresh_time = timezone.now() - timezone.timedelta(hours=1)

        self.target_user.last_login = login_time
        self.target_user.save(update_fields=["last_login"])

        device = TrustedDevice.objects.create(
            user=self.target_user,
            bundle_id="cn.Zhaodk.Health",
            device_id="device-last-used",
        )
        TrustedDevice.objects.filter(pk=device.pk).update(last_seen=device_time)

        session_device = TrustedDevice.objects.create(
            user=self.target_user,
            bundle_id="cn.Zhaodk.Health",
            device_id="device-session",
        )
        TrustedDevice.objects.filter(pk=session_device.pk).update(last_seen=device_time)
        AccountDeviceSession.objects.create(
            user=self.target_user,
            trusted_device=session_device,
            bundle_id=session_device.bundle_id,
            device_id=session_device.device_id,
            status=AccountDeviceSession.Status.LOGGED_OUT,
            last_refreshed_at=refresh_time,
        )

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/users/")
        self.assertEqual(response.status_code, 200)
        items = response.data["data"]["items"]
        row = next(item for item in items if item["id"] == self.target_user.id)
        last_used = row["last_used_at"]
        self.assertIsNotNone(last_used)
        if isinstance(last_used, str):
            from django.utils.dateparse import parse_datetime

            last_used = parse_datetime(last_used)
        self.assertEqual(last_used.replace(microsecond=0), refresh_time.replace(microsecond=0))


class AdminAIScenarioMultiAgentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = User.objects.create_user(
            username="ai_staff",
            email="ai-staff@example.com",
            password="pass1234",
            is_staff=True,
        )
        bootstrap_admin_permissions()
        super_admin = AdminRole.objects.get(code="super_admin")
        AdminUserRole.objects.create(user=self.staff_user, role=super_admin)
        self.client.force_authenticate(user=self.staff_user)

        from ai_config.models import AIModelCatalog, AIProviderKeyConfig, IdentityKind, ScenarioKey

        AIProviderKeyConfig.objects.create(
            kind=AIProviderKeyConfig.Kind.API,
            name="Test Provider",
            company="TESTCO",
            key="test-key",
            request_url="https://api.example.com/v1",
            is_using=True,
        )
        self.catalog_model = AIModelCatalog.objects.create(
            name="doubao-seed-2-0-pro-260215",
            display_name="Doubao Seed 2.0 Pro",
            company="TESTCO",
        )
        self.scenario_key = ScenarioKey.CHAT
        self.agent_identity = IdentityKind.AGENT

    def test_create_multiple_agents_for_same_base_model(self):
        payload = {
            "model": self.catalog_model.name,
            "display_name": "报告解读助手",
            "identity": self.agent_identity,
            "temperature": 0.2,
            "max_tokens": 2048,
            "position": 1,
            "is_active": True,
        }
        first = self.client.post(
            f"/api/admin/v1/ai/scenarios/{self.scenario_key}/models/",
            payload,
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)

        second = self.client.post(
            f"/api/admin/v1/ai/scenarios/{self.scenario_key}/models/",
            {**payload, "display_name": "用药建议助手", "position": 2, "brief_description": "第二个智能体"},
            format="json",
        )
        self.assertEqual(second.status_code, 201, second.data)
        self.assertNotEqual(first.data["data"]["id"], second.data["data"]["id"])
        self.assertNotEqual(first.data["data"]["bootstrap_name"], second.data["data"]["bootstrap_name"])
        self.assertEqual(first.data["data"]["display_name"], "报告解读助手")
        self.assertEqual(second.data["data"]["display_name"], "用药建议助手")

    def test_create_binding_allows_empty_display_name(self):
        response = self.client.post(
            f"/api/admin/v1/ai/scenarios/{self.scenario_key}/models/",
            {
                "model": self.catalog_model.name,
                "display_name": "   ",
                "identity": self.agent_identity,
                "temperature": 0.2,
                "max_tokens": 2048,
                "position": 1,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["data"]["display_name"], "")

    def test_update_binding_display_name(self):
        create_resp = self.client.post(
            f"/api/admin/v1/ai/scenarios/{self.scenario_key}/models/",
            {
                "model": self.catalog_model.name,
                "display_name": "初始名称",
                "identity": self.agent_identity,
                "temperature": 0.2,
                "max_tokens": 2048,
                "position": 1,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201, create_resp.data)
        binding_id = create_resp.data["data"]["id"]

        update_resp = self.client.patch(
            f"/api/admin/v1/ai/scenario-models/{binding_id}/",
            {"display_name": "更新后的名称"},
            format="json",
        )
        self.assertEqual(update_resp.status_code, 200, update_resp.data)
        self.assertEqual(update_resp.data["data"]["display_name"], "更新后的名称")

    def test_create_duplicate_model_binding_still_rejected(self):
        payload = {
            "model": self.catalog_model.name,
            "display_name": "Doubao 对话模型",
            "identity": "model",
            "temperature": 0.2,
            "max_tokens": 2048,
            "position": 1,
            "is_active": True,
        }
        first = self.client.post(
            f"/api/admin/v1/ai/scenarios/{self.scenario_key}/models/",
            payload,
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)

        second = self.client.post(
            f"/api/admin/v1/ai/scenarios/{self.scenario_key}/models/",
            {**payload, "position": 2},
            format="json",
        )
        self.assertEqual(second.status_code, 400)
        self.assertIn("model_already_bound_to_this_scenario_with_same_identity", str(second.data))
