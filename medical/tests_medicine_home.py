from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from medical.models import MedicationPlan, MedicationRecord, MedicineBox, Member, UserMemberBinding


User = get_user_model()


class MedicineHomeAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="medicine-home", password="test123456")
        self.member = Member.objects.create(user=self.user, name="小明", is_primary=True)
        UserMemberBinding.objects.create(user=self.user, member=self.member, role=UserMemberBinding.Role.OWNER)
        self.client.force_authenticate(self.user)

    def test_home_returns_summary_and_medicine_items(self):
        MedicineBox.objects.create(
            user=self.user,
            member=self.member,
            medicine_name="儿童退烧药",
            dose_unit="毫升",
            total_quantity=10,
            expire_date=timezone.localdate(),
        )
        response = self.client.get(f"/api/v1/medical/medicine-cabinet/home/?member_id={self.member.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()["data"]
        self.assertEqual(body["summary"]["medicine_count"], 1)
        self.assertEqual(body["medicines"][0]["medicine_name"], "儿童退烧药")
        self.assertIn("ETag", response)

    def test_search_requires_permission_and_matches_name(self):
        MedicineBox.objects.create(user=self.user, member=self.member, medicine_name="维生素D")
        response = self.client.get(f"/api/v1/medical/medicine-cabinet/search/?member_id={self.member.id}&q=维生素")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]["items"]), 1)

    def test_mark_taken_consumes_inventory_once(self):
        box = MedicineBox.objects.create(user=self.user, member=self.member, medicine_name="降压药", total_quantity=5, dose_unit="片")
        plan = MedicationPlan.objects.create(
            user=self.user,
            member=self.member,
            medicine_box=box,
            drug_name="降压药",
            dose_per_time="1片",
            dose_value=1,
            dose_unit="片",
            frequency_text="每天一次",
            start_date=timezone.localdate(),
        )
        record = MedicationRecord.objects.create(
            user=self.user,
            member=self.member,
            plan=plan,
            scheduled_at=timezone.make_aware(datetime.combine(timezone.localdate(), time(8))),
            status=MedicationRecord.Status.SCHEDULED,
            planned_dose="1片",
        )
        url = f"/api/v1/medical/medication-records/{record.id}/mark-taken/"
        self.assertEqual(self.client.post(url, {}, format="json").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, status.HTTP_200_OK)
        self.assertEqual(MedicineBox.objects.get(id=box.id).total_quantity, 4)
