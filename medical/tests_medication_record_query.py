from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from medical.models import MedicationPlan, MedicationRecord, Member

User = get_user_model()


class MedicationRecordScheduledRangeAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="med_record_range_tester",
            email="range@example.com",
            password="test123456",
        )
        self.client.force_authenticate(self.user)

        create_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "测试成员", "gender": "male", "relationship": "self"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.member_id = create_resp.json()["data"]["id"]
        self.member = Member.objects.get(id=self.member_id)

        self.plan = MedicationPlan.objects.create(
            user=self.user,
            member=self.member,
            drug_name="测试药",
            dose_per_time="1片",
            dose_unit="片",
            frequency_text="每日一次",
            start_date=timezone.localdate() - timedelta(days=30),
            status=MedicationPlan.Status.ACTIVE,
        )

        tz = timezone.get_current_timezone()
        self.center_day = timezone.localdate()
        self.day_minus_5 = timezone.make_aware(
            datetime.combine(self.center_day - timedelta(days=5), time(hour=8, minute=0)),
            tz,
        )
        self.day_minus_1 = timezone.make_aware(
            datetime.combine(self.center_day - timedelta(days=1), time(hour=8, minute=0)),
            tz,
        )
        self.day_center = timezone.make_aware(
            datetime.combine(self.center_day, time(hour=8, minute=0)),
            tz,
        )
        self.day_plus_4 = timezone.make_aware(
            datetime.combine(self.center_day + timedelta(days=4), time(hour=20, minute=0)),
            tz,
        )
        self.day_plus_5_midnight = timezone.make_aware(
            datetime.combine(self.center_day + timedelta(days=5), time.min),
            tz,
        )

        for scheduled_at in (
            self.day_minus_5,
            self.day_minus_1,
            self.day_center,
            self.day_plus_4,
            self.day_plus_5_midnight,
        ):
            MedicationRecord.objects.create(
                user=self.user,
                member=self.member,
                plan=self.plan,
                scheduled_at=scheduled_at,
                status=MedicationRecord.Status.SCHEDULED,
                planned_dose="1片",
                dose_sequence=1,
            )

    def _list_records(self, **query):
        params = {"kind": "medication-records", "member_id": str(self.member_id), **query}
        return self.client.get("/api/v1/medical/resources/", params)

    def test_scheduled_range_returns_nine_day_window_records(self):
        window_start = timezone.make_aware(
            datetime.combine(self.center_day - timedelta(days=4), time.min),
            timezone.get_current_timezone(),
        )
        window_end_exclusive = timezone.make_aware(
            datetime.combine(self.center_day + timedelta(days=5), time.min),
            timezone.get_current_timezone(),
        )

        response = self._list_records(
            scheduled_from=window_start.isoformat(),
            scheduled_to=window_end_exclusive.isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids_by_day = {record["scheduled_at"][:10] for record in response.json()["data"]}
        self.assertEqual(len(response.json()["data"]), 3)
        self.assertIn(self.day_minus_1.date().isoformat(), ids_by_day)
        self.assertIn(self.day_center.date().isoformat(), ids_by_day)
        self.assertIn(self.day_plus_4.date().isoformat(), ids_by_day)

    def test_scheduled_to_is_exclusive_upper_bound(self):
        window_start = timezone.make_aware(
            datetime.combine(self.center_day - timedelta(days=4), time.min),
            timezone.get_current_timezone(),
        )
        window_end_exclusive = self.day_plus_5_midnight.isoformat()

        response = self._list_records(
            scheduled_from=window_start.isoformat(),
            scheduled_to=window_end_exclusive,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        scheduled_dates = {item["scheduled_at"][:10] for item in response.json()["data"]}
        self.assertNotIn(self.day_plus_5_midnight.date().isoformat(), scheduled_dates)

    def test_invalid_scheduled_range_returns_400(self):
        window_start = timezone.make_aware(
            datetime.combine(self.center_day + timedelta(days=2), time.min),
            timezone.get_current_timezone(),
        )
        window_end_exclusive = timezone.make_aware(
            datetime.combine(self.center_day, time.min),
            timezone.get_current_timezone(),
        )

        response = self._list_records(
            scheduled_from=window_start.isoformat(),
            scheduled_to=window_end_exclusive.isoformat(),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["msg"], "invalid_scheduled_range")
