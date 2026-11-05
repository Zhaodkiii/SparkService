from datetime import timedelta
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.exceptions import APIError
from .models import ProductionPolicy, ProductionTask, ProductionWindow, ProductionLedger
from .services import quota, start, transition, settle_verified_result


class ProductionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="maker", password="test")
        self.policy = ProductionPolicy.objects.create(name="test", short_limit=2, weekly_limit=3, reason="test")
        self.key = uuid.uuid4()

    def make(self, key=None):
        return start(self.user, key or uuid.uuid4(), "a" * 64)

    def test_double_start_and_digest_conflict(self):
        first = self.make(self.key)
        self.assertEqual(first.pk, self.make(self.key).pk)
        self.assertEqual(ProductionLedger.objects.count(), 1)
        with self.assertRaises(APIError):
            start(self.user, self.key, "b" * 64)

    def test_short_window_blocks_without_partial_write(self):
        self.make()
        self.make()
        with self.assertRaises(APIError):
            self.make()
        self.assertEqual(ProductionTask.objects.count(), 2)
        self.assertEqual(list(ProductionWindow.objects.values_list("reserved", flat=True)), [2, 2])

    def test_complete_is_idempotent_and_survives_window_boundary(self):
        task = self.make()
        with patch("ai_production.services.timezone.now", return_value=timezone.now() + timedelta(hours=6)):
            settle_verified_result(self.user, task.pk, {"asset": "verified"})
            settle_verified_result(self.user, task.pk, {"asset": "verified"})
            current = quota(self.user)
        self.assertEqual(current["windows"][0]["used"], 0)
        self.assertEqual(current["windows"][1]["used"], 1)
        self.assertEqual(ProductionLedger.objects.filter(event="settle").count(), 1)

    def test_cancel_repeated_and_late_completion(self):
        task = self.make()
        transition(self.user, task.pk, "cancel", task.version)
        transition(self.user, task.pk, "cancel", task.version)
        with self.assertRaises(APIError):
            settle_verified_result(self.user, task.pk, {"asset": "late"})
        self.assertEqual(quota(self.user)["windows"][0]["available"], 2)

    def test_pause_continue_no_new_reservation(self):
        task = self.make()
        paused = transition(self.user, task.pk, "pause", task.version)
        resumed = transition(self.user, task.pk, "resume", paused.version)
        self.assertEqual(resumed.state, "reserved")
        self.assertEqual(ProductionLedger.objects.filter(event="reserve").count(), 1)

    def test_expiry_releases_both_and_resume_reserves_again(self):
        task = self.make()
        future = timezone.now() + timedelta(hours=25)
        with patch("ai_production.services.timezone.now", return_value=future):
            quota(self.user)
            task.refresh_from_db()
            self.assertEqual(task.state, "expired")
            resumed = transition(self.user, task.pk, "resume", task.version)
            self.assertEqual(resumed.state, "reserved")
        self.assertEqual(ProductionLedger.objects.filter(event="reserve").count(), 2)

    def test_api_rejects_foreign_task_and_invalid_payload(self):
        task = self.make()
        other = get_user_model().objects.create_user(username="other")
        client = APIClient()
        client.force_authenticate(other)
        self.assertEqual(client.get(f"/api/v1/ai-production/tasks/{task.pk}/").status_code, 404)
        self.assertEqual(client.post("/api/v1/ai-production/tasks/", {}, format="json").status_code, 400)

    def test_policy_change_preserves_current_window(self):
        self.make()
        ProductionPolicy.objects.create(name="new", short_limit=9, weekly_limit=20, reason="upgrade")
        self.assertEqual(quota(self.user)["windows"][0]["limit"], 2)

    def test_refund_is_once_and_keeps_result(self):
        from .services import refund
        task = self.make()
        settle_verified_result(self.user, task.pk, {"asset": "verified"})
        refund(self.user, task.pk, "客服退款")
        refund(self.user, task.pk, "重复点击")
        self.assertEqual(quota(self.user)["windows"][0]["used"], 0)
        self.assertEqual(ProductionLedger.objects.filter(event="refund").count(), 1)
        task.refresh_from_db()
        self.assertEqual(task.result, {"asset": "verified"})

    def test_admin_denies_customer(self):
        client = APIClient()
        client.force_authenticate(self.user)
        self.assertEqual(client.get("/api/admin/v1/ai-production/").status_code, 403)





    def test_confirmed_test_policy_is_three_and_ten(self):
        from django.core.management import call_command
        from django.test import override_settings
        with override_settings(DEBUG=True):
            call_command("configure_production_test_quota", verbosity=0)
            call_command("configure_production_test_quota", verbosity=0)
        policy = ProductionPolicy.objects.get(name="制作额度联调 3/10")
        self.assertEqual((policy.short_limit, policy.weekly_limit), (3, 10))

    def test_admin_publish_and_release_are_audited(self):
        from backoffice.models import AdminAuditLog
        admin = get_user_model().objects.create_superuser(username="quota-admin", password="test")
        client = APIClient()
        client.force_authenticate(admin)
        response = client.post("/api/admin/v1/ai-production/", {
            "name": "approved", "short_limit": 3, "weekly_limit": 10,
            "hold_hours": 24, "enabled": True, "reason": "确认测试",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        task = self.make()
        url = f"/api/admin/v1/ai-production/{task.pk}/release/"
        self.assertEqual(client.post(url, {"reason": "确认失败"}, format="json").status_code, 200)
        self.assertEqual(client.post(url, {"reason": "重复点击"}, format="json").status_code, 200)
        self.assertEqual(ProductionLedger.objects.filter(event="release").count(), 1)
        self.assertTrue(AdminAuditLog.objects.filter(action="production.policy.publish").exists())

    def test_user_anchored_windows_and_idle_restart(self):
        t = timezone.now()
        with patch("ai_production.services.timezone.now", return_value=t):
            self.make()
            before = quota(self.user)
        with patch("ai_production.services.timezone.now", return_value=t + timedelta(hours=2)):
            self.make()
            self.assertEqual(quota(self.user)["windows"][0]["reset_at"], before["windows"][0]["reset_at"])
        with patch("ai_production.services.timezone.now", return_value=t + timedelta(hours=5)):
            snapshot = quota(self.user)
            self.assertEqual(snapshot["windows"][0]["status"], "awaiting_first_use")
            self.assertIsNone(snapshot["windows"][0]["reset_at"])
            self.assertEqual(ProductionWindow.objects.count(), 2)
        with patch("ai_production.services.timezone.now", return_value=t + timedelta(hours=8)):
            self.make()
            snapshot = quota(self.user)
            self.assertEqual(snapshot["windows"][0]["reset_at"], (t + timedelta(hours=13)).isoformat())
            self.assertEqual(snapshot["windows"][1]["reset_at"], before["windows"][1]["reset_at"])

    def test_weekly_block_does_not_start_short_window(self):
        self.policy.weekly_limit = 1
        self.policy.save()
        t = timezone.now()
        with patch("ai_production.services.timezone.now", return_value=t):
            self.make()
        with patch("ai_production.services.timezone.now", return_value=t + timedelta(hours=6)):
            with self.assertRaises(APIError):
                self.make()
            snapshot = quota(self.user)
            self.assertIsNone(snapshot["windows"][0]["window_id"])
            self.assertEqual(snapshot["next_eligible_at"], (t + timedelta(days=7)).isoformat())
        self.assertEqual(ProductionWindow.objects.count(), 2)

    def test_policy_publish_replay_and_conflicting_content(self):
        admin = get_user_model().objects.create_superuser(username="publisher", password="test")
        client = APIClient()
        client.force_authenticate(admin)
        body = {"publish_key": str(uuid.uuid4()), "name": "replay", "short_limit": 3,
                "weekly_limit": 10, "hold_hours": 24, "enabled": True, "reason": "test"}
        url = "/api/admin/v1/ai-production/"
        first = client.post(url, body, format="json")
        self.assertEqual(first.status_code, 200)
        second = client.post(url, body, format="json")
        self.assertEqual(first.data["data"]["id"], second.data["data"]["id"])
        body["short_limit"] = 4
        self.assertEqual(client.post(url, body, format="json").status_code, 400)

    def test_maintenance_keeps_quota_readable_and_existing_resume(self):
        from .models import ProductionControl
        task = self.make()
        paused = transition(self.user, task.pk, "pause", task.version)
        ProductionControl.objects.create(pk=1, accepting=False, reason="test")
        snapshot = quota(self.user)
        self.assertFalse(snapshot["can_start"])
        self.assertIsNone(snapshot["next_eligible_at"])
        self.assertEqual(snapshot["service_status"], "maintenance")
        self.assertEqual(transition(self.user, task.pk, "resume", paused.version).state, "reserved")
        with self.assertRaises(APIError):
            self.make()

    def test_uppercase_uuid_routes_and_resumes_existing_task(self):
        from django.urls import resolve
        task = self.make()
        client = APIClient()
        client.force_authenticate(self.user)
        upper = str(task.pk).upper()
        response = client.get(f"/api/v1/ai-production/tasks/{upper}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["id"], str(task.pk))
        for suffix in ("complete/", "resume/"):
            match = resolve(f"/api/v1/ai-production/tasks/{upper}/{suffix}")
            self.assertEqual(match.kwargs["task_id"], task.pk)
        resumed = client.post(f"/api/v1/ai-production/tasks/{upper}/resume/",
                              {"version": task.version}, format="json")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(ProductionTask.objects.count(), 1)

    def test_client_completed_task_settles_once_without_provider_or_assets(self):
        task = self.make()
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/v1/ai-production/tasks/{str(task.pk).upper()}/complete/"
        body = {"digest": "a" * 64}
        first = client.post(url, body, format="json")
        second = client.post(url, body, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["data"]["state"], "completed")
        self.assertEqual(quota(self.user)["windows"][0]["used"], 1)
        self.assertEqual(ProductionLedger.objects.filter(event="settle").count(), 1)
        self.assertEqual(client.post(url, {"digest": "b" * 64}, format="json").status_code, 409)

    def test_proxy_routes_are_removed(self):
        task = self.make()
        client = APIClient()
        client.force_authenticate(self.user)
        for suffix in ("provider", "result"):
            response = client.post(f"/api/v1/ai-production/tasks/{task.pk}/{suffix}/", {}, format="json")
            self.assertEqual(response.status_code, 404)

    def test_reset_retains_running_task_and_restarts_only_selected_window(self):
        from .services import reset_quota
        task = self.make()
        old_short, old_week = task.short_window_id, task.weekly_window_id
        key = uuid.uuid4()
        reset = reset_quota(self.user, self.user, key, "short", "客服重置")
        again = reset_quota(self.user, self.user, key, "short", "客服重置")
        self.assertEqual(reset.pk, again.pk)
        snapshot = quota(self.user)
        self.assertEqual(snapshot["windows"][0]["available"], 2)
        self.assertIsNone(snapshot["windows"][0]["reset_at"])
        self.assertEqual(snapshot["windows"][1]["reserved"], 1)
        new = self.make()
        self.assertNotEqual(new.short_window_id, old_short)
        self.assertEqual(new.weekly_window_id, old_week)
        settle_verified_result(self.user, task.pk, {"digest":"a"*64})
        old = ProductionWindow.objects.get(pk=old_short)
        self.assertEqual((old.used, old.reserved), (1, 0))
        self.assertEqual(quota(self.user)["windows"][0]["used"], 0)

    def test_reset_api_permission_audit_and_replay(self):
        from .models import ProductionQuotaReset
        from backoffice.models import AdminAuditLog
        admin = get_user_model().objects.create_superuser(username="reset-admin", password="test")
        self.make()
        client = APIClient()
        url = f"/api/admin/v1/ai-production/users/{self.user.pk}/reset/"
        body = {"request_key":str(uuid.uuid4()),"scope":"both","reason":"开发验收"}
        client.force_authenticate(self.user)
        self.assertEqual(client.post(url, body, format="json").status_code, 403)
        client.force_authenticate(admin)
        response = client.post(url, body, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["quota"]["windows"][0]["available"], 2)
        self.assertEqual(client.post(url, body, format="json").status_code, 200)
        self.assertEqual(ProductionQuotaReset.objects.count(), 1)
        self.assertTrue(AdminAuditLog.objects.filter(action="production.quota.reset").exists())
        body["scope"]="short"
        self.assertEqual(client.post(url, body, format="json").status_code, 409)
        body["request_key"]=str(uuid.uuid4())
        body["reason"]=" "
        self.assertEqual(client.post(url, body, format="json").status_code, 400)
