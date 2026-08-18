from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from unittest.mock import patch

from accounts.models import AccessDenyEntry, SocialIdentity
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

    def test_user_list_returns_display_name(self):
        self.target_user.first_name = "哈哈哈哈 Dream"
        self.target_user.save(update_fields=["first_name"])

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/users/")
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data["data"]["items"] if item["id"] == self.target_user.id)
        self.assertEqual(row["display_name"], "哈哈哈哈 Dream")
        self.assertEqual(row["username"], "target_user")

    def test_user_detail_returns_display_name(self):
        self.target_user.first_name = "哈哈哈哈 Dream"
        self.target_user.save(update_fields=["first_name"])

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["user"]["display_name"], "哈哈哈哈 Dream")

    def test_user_list_search_by_display_name(self):
        self.target_user.first_name = "哈哈哈哈 Dream"
        self.target_user.save(update_fields=["first_name"])

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/users/", {"q": "哈哈哈哈"})
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["data"]["items"]}
        self.assertIn(self.target_user.id, ids)

    def test_user_list_sort_by_id(self):
        older = User.objects.create_user(username="older_u", email="older@example.com", password="pass1234")
        newer = User.objects.create_user(username="newer_u", email="newer@example.com", password="pass1234")
        self.client.force_authenticate(user=self.staff_user)

        asc = self.client.get("/api/admin/v1/users/", {"sort_by": "id", "order": "asc", "page_size": 100})
        self.assertEqual(asc.status_code, 200)
        asc_ids = [item["id"] for item in asc.data["data"]["items"]]
        self.assertLess(asc_ids.index(older.id), asc_ids.index(newer.id))

        desc = self.client.get("/api/admin/v1/users/", {"sort_by": "id", "order": "desc", "page_size": 100})
        self.assertEqual(desc.status_code, 200)
        desc_ids = [item["id"] for item in desc.data["data"]["items"]]
        self.assertLess(desc_ids.index(newer.id), desc_ids.index(older.id))

    def test_user_list_sort_by_date_joined_and_invalid_fallback(self):
        from django.utils import timezone

        early = User.objects.create_user(username="early_u", email="early@example.com", password="pass1234")
        late = User.objects.create_user(username="late_u", email="late@example.com", password="pass1234")
        User.objects.filter(pk=early.pk).update(date_joined=timezone.now() - timezone.timedelta(days=3))
        User.objects.filter(pk=late.pk).update(date_joined=timezone.now() - timezone.timedelta(days=1))

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(
            "/api/admin/v1/users/",
            {"sort_by": "date_joined", "order": "desc", "page_size": 100},
        )
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data["data"]["items"]]
        self.assertLess(ids.index(late.id), ids.index(early.id))

        invalid = self.client.get(
            "/api/admin/v1/users/",
            {"sort_by": "hack", "order": "nope", "page_size": 100},
        )
        self.assertEqual(invalid.status_code, 200)
        invalid_ids = [item["id"] for item in invalid.data["data"]["items"]]
        self.assertLess(invalid_ids.index(late.id), invalid_ids.index(early.id))

    def test_user_list_sort_by_last_used_at_nulls_last(self):
        from django.utils import timezone

        active_user = User.objects.create_user(username="active_u", email="active@example.com", password="pass1234")
        idle_user = User.objects.create_user(username="idle_u", email="idle@example.com", password="pass1234")
        seen = timezone.now() - timezone.timedelta(hours=1)
        device = TrustedDevice.objects.create(
            user=active_user,
            bundle_id="cn.Zhaodk.Health",
            device_id="device-sort-active",
        )
        TrustedDevice.objects.filter(pk=device.pk).update(last_seen=seen)

        self.client.force_authenticate(user=self.staff_user)
        desc = self.client.get(
            "/api/admin/v1/users/",
            {"sort_by": "last_used_at", "order": "desc", "page_size": 100},
        )
        self.assertEqual(desc.status_code, 200)
        desc_ids = [item["id"] for item in desc.data["data"]["items"]]
        self.assertLess(desc_ids.index(active_user.id), desc_ids.index(idle_user.id))

        asc = self.client.get(
            "/api/admin/v1/users/",
            {"sort_by": "last_used_at", "order": "asc", "page_size": 100},
        )
        self.assertEqual(asc.status_code, 200)
        asc_ids = [item["id"] for item in asc.data["data"]["items"]]
        self.assertLess(asc_ids.index(active_user.id), asc_ids.index(idle_user.id))

    def test_user_list_includes_pro_fields(self):
        from django.utils import timezone
        from ai_config.models import TrialApplication

        TrialApplication.objects.create(
            user=self.target_user,
            status=TrialApplication.Status.ACTIVE,
            grant_source=TrialApplication.GrantSource.MANUAL,
            started_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/users/")
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data["data"]["items"] if item["id"] == self.target_user.id)
        self.assertTrue(row["is_pro"])
        self.assertEqual(row["pro_status"], "active")
        self.assertIsNotNone(row["pro_expires_at"])

    def test_user_detail_includes_pro_and_app_version(self):
        from django.utils import timezone
        from ai_config.models import TrialApplication

        TrialApplication.objects.create(
            user=self.target_user,
            status=TrialApplication.Status.ACTIVE,
            grant_source=TrialApplication.GrantSource.MANUAL,
            started_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(days=10),
        )
        TrustedDevice.objects.create(
            user=self.target_user,
            bundle_id="cn.Zhaodk.Health",
            device_id="device-version",
            app_version="1.4.2",
            build_version="102",
            bundle_identifier="cn.Zhaodk.Health",
        )
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertTrue(data["pro"]["is_pro"])
        self.assertEqual(data["pro"]["status"], "active")
        self.assertTrue(data["user"]["is_pro"])
        self.assertEqual(data["trusted_devices"][0]["app_version"], "1.4.2")
        self.assertEqual(data["trusted_devices"][0]["build_version"], "102")

    def test_user_detail_pro_none_when_missing(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 200)
        pro = response.data["data"]["pro"]
        self.assertFalse(pro["is_pro"])
        self.assertEqual(pro["status"], "none")
        self.assertIsNone(pro["trial_id"])

    def test_user_pro_grant_and_recycle(self):
        self.client.force_authenticate(user=self.staff_user)
        grant = self.client.post(
            f"/api/admin/v1/users/{self.target_user.id}/pro/grant/",
            {"grant_days": 15, "note": "客服补偿"},
            format="json",
        )
        self.assertEqual(grant.status_code, 200, grant.data)
        self.assertTrue(grant.data["data"]["pro"]["is_pro"])
        self.assertEqual(grant.data["data"]["pro"]["status"], "active")

        recycle = self.client.post(
            f"/api/admin/v1/users/{self.target_user.id}/pro/recycle/",
            {"note": "误发回收"},
            format="json",
        )
        self.assertEqual(recycle.status_code, 200, recycle.data)
        self.assertFalse(recycle.data["data"]["pro"]["is_pro"])
        self.assertEqual(recycle.data["data"]["pro"]["status"], "expired")

        audits = AdminAuditLog.objects.filter(
            action__in=["admin.user.pro.grant", "admin.user.pro.recycle"],
            resource_id=str(self.target_user.id),
        )
        self.assertEqual(audits.count(), 2)

    def test_user_pro_recycle_without_record_returns_400(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            f"/api/admin/v1/users/{self.target_user.id}/pro/recycle/",
            {"note": "无记录"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "pro_not_found")

    def test_user_pro_grant_requires_permission(self):
        limited = User.objects.create_user(
            username="limited_staff",
            email="limited@example.com",
            password="pass1234",
            is_staff=True,
        )
        self.client.force_authenticate(user=limited)
        response = self.client.post(
            f"/api/admin/v1/users/{self.target_user.id}/pro/grant/",
            {"grant_days": 7},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_user_list_filter_by_bundle_id_device(self):
        bundle = "cn.Zhaodk.Health"
        TrustedDevice.objects.create(
            user=self.target_user,
            bundle_id=bundle,
            device_id="bundle-filter-device",
        )
        other = User.objects.create_user(username="other_bundle", email="other@example.com", password="pass1234")

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/users/", {"bundle_id": bundle, "page_size": 100})
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["data"]["items"]}
        self.assertIn(self.target_user.id, ids)
        self.assertNotIn(other.id, ids)

    def test_user_list_filter_by_bundle_id_session(self):
        bundle = "cn.Zhaodk.Session"
        device = TrustedDevice.objects.create(
            user=self.target_user,
            bundle_id=bundle,
            device_id="bundle-session-device",
        )
        AccountDeviceSession.objects.create(
            user=self.target_user,
            trusted_device=device,
            bundle_id=bundle,
            device_id=device.device_id,
        )
        other = User.objects.create_user(username="other_session", email="sess@example.com", password="pass1234")

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/users/", {"bundle_id": bundle, "page_size": 100})
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["data"]["items"]}
        self.assertIn(self.target_user.id, ids)
        self.assertNotIn(other.id, ids)

    def test_user_list_filter_by_date_joined_range(self):
        from django.utils import timezone

        early = User.objects.create_user(username="joined_early", email="early2@example.com", password="pass1234")
        late = User.objects.create_user(username="joined_late", email="late2@example.com", password="pass1234")
        mid = timezone.now() - timezone.timedelta(days=5)
        User.objects.filter(pk=early.pk).update(date_joined=mid - timezone.timedelta(days=10))
        User.objects.filter(pk=late.pk).update(date_joined=mid + timezone.timedelta(days=10))
        User.objects.filter(pk=self.target_user.pk).update(date_joined=mid)

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(
            "/api/admin/v1/users/",
            {
                "date_joined_after": (mid - timezone.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                "date_joined_before": (mid + timezone.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                "page_size": 100,
            },
        )
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["data"]["items"]}
        self.assertIn(self.target_user.id, ids)
        self.assertNotIn(early.id, ids)
        self.assertNotIn(late.id, ids)

    def test_user_list_filter_by_last_used_range(self):
        from django.utils import timezone

        active_user = User.objects.create_user(username="used_active", email="used@example.com", password="pass1234")
        idle_user = User.objects.create_user(username="used_idle", email="idle2@example.com", password="pass1234")
        seen = timezone.now() - timezone.timedelta(hours=2)
        device = TrustedDevice.objects.create(
            user=active_user,
            bundle_id="cn.Zhaodk.Health",
            device_id="last-used-filter",
        )
        TrustedDevice.objects.filter(pk=device.pk).update(last_seen=seen)

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(
            "/api/admin/v1/users/",
            {
                "last_used_after": (seen - timezone.timedelta(hours=1)).isoformat(),
                "last_used_before": (seen + timezone.timedelta(hours=1)).isoformat(),
                "page_size": 100,
            },
        )
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["data"]["items"]}
        self.assertIn(active_user.id, ids)
        self.assertNotIn(idle_user.id, ids)

    def test_user_list_invalid_datetime_returns_400(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/users/", {"date_joined_after": "not-a-date"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "invalid_datetime_param")
        self.assertEqual(response.data["data"]["field"], "date_joined_after")

    def test_user_detail_returns_auth_identities_masked(self):
        from accounts.models import SocialIdentity

        SocialIdentity.objects.create(
            user=self.target_user,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple_000082.abcdef123456",
            bundle_id="cn.Zhaodk.Health",
        )
        SocialIdentity.objects.create(
            user=self.target_user,
            provider=SocialIdentity.Provider.EMAIL,
            provider_uid="97621528@qq.com",
            bundle_id="cn.Zhaodk.Health",
        )

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 200)
        identities = response.data["data"]["auth_identities"]
        self.assertEqual(len(identities), 2)
        apple = next(item for item in identities if item["provider"] == "apple")
        email = next(item for item in identities if item["provider"] == "email")
        self.assertEqual(apple["provider_label"], "Apple")
        self.assertIn("...", apple["provider_uid_masked"])
        self.assertNotEqual(apple["provider_uid_masked"], "apple_000082.abcdef123456")
        self.assertIn("***", email["provider_uid_masked"])
        self.assertNotIn("provider_uid", apple)

    def test_user_detail_auth_identities_empty(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["auth_identities"], [])


class AdminSortingHelperTests(TestCase):
    def test_resolve_admin_sort_whitelist_and_fallback(self):
        from types import SimpleNamespace
        from backoffice.sorting import resolve_admin_sort

        allowed = {
            "id": {"asc": ["id"], "desc": ["-id"]},
            "date_joined": {"asc": ["date_joined", "id"], "desc": ["-date_joined", "-id"]},
        }
        request = SimpleNamespace(query_params={"sort_by": "id", "order": "asc"})
        self.assertEqual(resolve_admin_sort(request, allowed=allowed, default=("date_joined", "desc")), ["id"])

        bad = SimpleNamespace(query_params={"sort_by": "x", "order": "desc"})
        self.assertEqual(
            resolve_admin_sort(bad, allowed=allowed, default=("date_joined", "desc")),
            ["-date_joined", "-id"],
        )


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

    def test_update_binding_base_model(self):
        from ai_config.models import AIModelCatalog

        other_model = AIModelCatalog.objects.create(
            name="deepseek-v4-pro",
            display_name="DeepSeek-V4-Pro",
            company="TESTCO",
        )
        create_resp = self.client.post(
            f"/api/admin/v1/ai/scenarios/{self.scenario_key}/models/",
            {
                "model": self.catalog_model.name,
                "display_name": "高级健康助手",
                "identity": self.agent_identity,
                "temperature": 0.8,
                "max_tokens": 12048,
                "position": 2,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201, create_resp.data)
        binding_id = create_resp.data["data"]["id"]
        old_bootstrap = create_resp.data["data"]["bootstrap_name"]

        update_resp = self.client.patch(
            f"/api/admin/v1/ai/scenario-models/{binding_id}/",
            {"model": other_model.name},
            format="json",
        )
        self.assertEqual(update_resp.status_code, 200, update_resp.data)
        self.assertEqual(update_resp.data["data"]["model"], other_model.name)
        self.assertEqual(update_resp.data["data"]["model_id"], other_model.id)
        self.assertNotEqual(update_resp.data["data"]["bootstrap_name"], old_bootstrap)
        self.assertIn(other_model.name, update_resp.data["data"]["bootstrap_name"])

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


class BackofficeBlacklistTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = User.objects.create_user(
            username="blacklist_staff",
            email="blacklist_staff@example.com",
            password="pass1234",
            is_staff=True,
        )
        self.target_user = User.objects.create_user(
            username="blacklist_target",
            email="blacklist_target@example.com",
            password="pass1234",
            is_staff=False,
            is_active=True,
        )
        bootstrap_admin_permissions()
        super_admin = AdminRole.objects.get(code="super_admin")
        AdminUserRole.objects.create(user=self.staff_user, role=super_admin)
        self.client.force_authenticate(user=self.staff_user)

    @patch("accounts.infrastructure.sms_provider.AliyunSMSProvider.send_account_banned")
    def test_create_blacklist_by_user_disables_account(self, mock_send):
        mock_send.return_value = type(
            "R",
            (),
            {"accepted": True, "reason": "", "biz_id": "biz-1", "request_id": "req-1", "code": "OK", "status": "accepted", "unknown": False, "payload": {}},
        )()
        response = self.client.post(
            "/api/admin/v1/users/blacklist/",
            {"user_id": self.target_user.id, "reason_note": "违规测试"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_active)
        self.assertTrue(AdminAuditLog.objects.filter(action="admin.user.blacklist.create").exists())

    def test_create_blacklist_by_phone_without_user(self):
        with patch("accounts.infrastructure.sms_provider.AliyunSMSProvider.send_account_banned") as mock_send:
            mock_send.return_value = type(
                "R",
                (),
                {"accepted": True, "reason": "", "biz_id": "biz-2", "request_id": "req-2", "code": "OK", "status": "accepted", "unknown": False, "payload": {}},
            )()
            response = self.client.post(
                "/api/admin/v1/users/blacklist/",
                {"phone": "13700137000"},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.PHONE,
                dimension_value="+8613700137000",
                revoked_at__isnull=True,
            ).exists()
        )

    @patch("accounts.infrastructure.sms_provider.AliyunSMSProvider.send_account_banned")
    def test_create_blacklist_by_phone_with_user_only_user_entry(self, mock_send):
        mock_send.return_value = type(
            "R",
            (),
            {"accepted": True, "reason": "", "biz_id": "biz-3", "request_id": "req-3", "code": "OK", "status": "accepted", "unknown": False, "payload": {}},
        )()
        SocialIdentity.objects.create(
            user=self.target_user,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8613800138000",
            bundle_id="cn.Zhaodk.Health",
        )
        response = self.client.post(
            "/api/admin/v1/users/blacklist/",
            {"phone": "13800138000"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_active)
        self.assertTrue(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.USER_ID,
                dimension_value=str(self.target_user.id),
                revoked_at__isnull=True,
            ).exists()
        )
        self.assertFalse(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.PHONE,
                dimension_value="+8613800138000",
                revoked_at__isnull=True,
            ).exists()
        )

    def test_user_list_search_by_phone(self):
        SocialIdentity.objects.create(
            user=self.target_user,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8613800138000",
            bundle_id="cn.Zhaodk.Health",
        )
        response = self.client.get("/api/admin/v1/users/", {"q": "13800138000"})
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["data"]["items"]]
        self.assertIn(self.target_user.id, ids)
        matched = next(row for row in response.data["data"]["items"] if row["id"] == self.target_user.id)
        self.assertEqual(matched.get("phone_number"), "+8613800138000")

    @patch("accounts.infrastructure.sms_provider.AliyunSMSProvider.send_account_banned")
    def test_blacklist_list_display_value_not_masked(self, mock_send):
        mock_send.return_value = type(
            "R",
            (),
            {"accepted": True, "reason": "", "biz_id": "biz-4", "request_id": "req-4", "code": "OK", "status": "accepted", "unknown": False, "payload": {}},
        )()
        self.client.post(
            "/api/admin/v1/users/blacklist/",
            {"phone": "13700137001"},
            format="json",
        )
        response = self.client.get("/api/admin/v1/users/blacklist/", {"active_only": "true"})
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data["data"]["items"] if item["dimension_value"] == "+8613700137001")
        self.assertEqual(row["display_value"], "+8613700137001")
        self.assertNotIn("*", row["display_value"])

    def test_cannot_ban_admin_user(self):
        admin_target = User.objects.create_user(
            username="admin_target",
            email="admin_target@example.com",
            password="pass1234",
            is_staff=True,
        )
        response = self.client.post(
            "/api/admin/v1/users/blacklist/",
            {"user_id": admin_target.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("accounts.infrastructure.sms_provider.AliyunSMSProvider.send_account_banned")
    def test_revoke_blacklist_entry(self, mock_send):
        mock_send.return_value = type(
            "R",
            (),
            {"accepted": False, "reason": "skipped", "biz_id": "", "request_id": "", "code": "", "status": "skipped", "unknown": False, "payload": {}},
        )()
        create_resp = self.client.post(
            "/api/admin/v1/users/blacklist/",
            {"user_id": self.target_user.id},
            format="json",
        )
        entry_id = create_resp.data["data"]["entry"]["id"]
        revoke_resp = self.client.post(f"/api/admin/v1/users/blacklist/{entry_id}/revoke/", {}, format="json")
        self.assertEqual(revoke_resp.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertTrue(self.target_user.is_active)
