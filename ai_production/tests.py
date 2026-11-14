from decimal import Decimal
from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ProductionCall, ProductionLedger, ProductionPolicy, ProductionTask, ProductionWindow
from .services import adjust, expire_account_calls, points, report, reset_quota


class UsageAccountingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="usage")
        self.admin = get_user_model().objects.create_superuser(username="usage-admin", password="test")
        self.policy = ProductionPolicy.objects.create(short_limit_points=100, weekly_limit_points=500)
        self.task = ProductionTask.objects.create(account=self.user, attempt_key=uuid.uuid4(), input_digest="a" * 64)
        now = timezone.now()
        self.windows = [
            ProductionWindow.objects.create(account=self.user, policy=self.policy, kind=kind, limit_points=limit,
                                            starts_at=now, ends_at=now + timedelta(hours=hours))
            for kind, limit, hours in (("short", 100, 5), ("weekly", 500, 168))
        ]
        self.rate = dict(category="text_ai", mode="tokens", input_rate="1", cached_input_rate="0.5",
                         output_rate="2", minimum_charge="0.2")
        self.call = ProductionCall.objects.create(id=uuid.uuid4(), task=self.task, policy=self.policy,
            short_window=self.windows[0], weekly_window=self.windows[1], rate=self.rate,
            scene="diary.layout", model="test", category="text_ai", budget=10,
            usage_due_at=now + timedelta(minutes=7))
        self.usage = dict(input_tokens=1000, cached_input_tokens=500, output_tokens=500)

    def report(self, event=None, usage=None, state="failed"):
        return report(self.user, self.task.pk, self.call.pk, event or uuid.uuid4(), state,
                      self.usage if usage is None else usage, "provider-request")

    def used(self):
        return list(ProductionWindow.objects.order_by("pk").values_list("used_points", flat=True))

    def test_failed_with_usage_charges_both_once(self):
        event = uuid.uuid4()
        self.report(event)
        self.report(event)
        self.report()
        self.assertEqual(self.used(), [Decimal("1.75")] * 2)
        self.assertEqual(ProductionLedger.objects.count(), 1)

    def test_failed_without_usage_gets_minimum_and_late_usage_replaces_estimate(self):
        event = uuid.uuid4()
        self.report(event, {})
        self.report(event, {})
        self.assertEqual(self.used(), [Decimal("0.2")] * 2)
        self.report()
        self.assertEqual(self.used(), [Decimal("1.75")] * 2)
        self.assertEqual(list(ProductionLedger.objects.order_by("pk").values_list("event", flat=True)),
                         ["charge", "measurement_adjustment"])

    def test_timeout_and_reset_keep_call_on_original_windows(self):
        self.call.usage_due_at = timezone.now() - timedelta(seconds=1)
        self.call.save(update_fields=["usage_due_at"])
        reset_quota(self.admin, self.user, uuid.uuid4(), "short", "test")
        expire_account_calls(self.user)
        expire_account_calls(self.user)
        self.assertEqual(self.used(), [Decimal("0.2")] * 2)
        self.assertLessEqual(ProductionWindow.objects.get(pk=self.windows[0].pk).ends_at, timezone.now())

    def test_image_supports_native_output_tokens_and_image_count(self):
        image = dict(self.rate, category="image_ai")
        self.assertEqual(points(image, {"output_tokens": 1500}, {}), Decimal(3))
        image.update(mode="images", image_rates={"2K": "1.7"})
        self.assertEqual(points(image, {"generated_images": 2}, {"size": "2K"}), Decimal("3.4"))

    def test_admin_correction_idempotent(self):
        self.report()
        event = uuid.uuid4()
        after = adjust(self.call.pk, event, 2, dict(input_tokens=0, output_tokens=500), "source checked")
        adjust(self.call.pk, event, 2, dict(input_tokens=0, output_tokens=500), "source checked")
        self.assertEqual(after.usage_source, "admin_verified")
        self.assertEqual(self.used(), [Decimal(1)] * 2)

    def test_user_quota_exposes_percentage_without_internal_points(self):
        api = APIClient()
        api.force_authenticate(self.user)
        self.report()
        response = api.get("/api/v1/ai-production/quota/")
        self.assertEqual(response.status_code, 200)
        window = response.data["data"]["windows"][0]
        self.assertAlmostEqual(window["remaining_ratio"], 0.9825)
        self.assertNotIn("used_points", window)

    def test_admin_publishes_model_rates_idempotently(self):
        api = APIClient()
        api.force_authenticate(self.admin)
        body = dict(name="Text and image", short_limit_points="100", weekly_limit_points="500",
                    publish_key=str(uuid.uuid4()), reason="test", rates={"model": self.rate})
        for _ in range(2):
            result = api.post("/api/admin/v1/ai-production/", body, format="json")
            self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(ProductionPolicy.objects.filter(name=body["name"]).count(), 1)


    def test_users_list_requires_positive_charge_history_even_after_reset(self):
        api = APIClient()
        api.force_authenticate(self.admin)
        url = "/api/admin/v1/ai-production/users/"

        self.assertEqual(api.get(url, {"q": self.user.pk}).data["data"]["items"], [])
        self.report()
        reset_quota(self.admin, self.user, uuid.uuid4(), "both", "test")

        data = api.get(url, {"page_size": 1}).data["data"]
        self.assertEqual(data["pagination"]["total"], 1)
        self.assertEqual([item["id"] for item in data["items"]], [self.user.pk])
        self.assertTrue(all(w["remaining_ratio"] == 1 for w in data["items"][0]["windows"]))
        self.assertEqual(api.get(url, {"q": self.admin.username}).data["data"]["items"], [])
