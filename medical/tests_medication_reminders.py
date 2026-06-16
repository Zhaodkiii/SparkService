from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from medical.models import (
    MedicationPlan,
    MedicationRecord,
    MedicationReminderLocalAuthorization,
    Member,
    UserMemberBinding,
)

User = get_user_model()


class MedicationReminderAuthorizationAPITests(APITestCase):
    def setUp(self):
        self.current_user = User.objects.create_user(
            username="current",
            email="current@example.com",
            password="pass12345",
        )
        self.owner_user = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="pass12345",
        )
        self.client.force_authenticate(self.current_user)

        self.self_member = self._create_member(
            owner=self.current_user,
            name="本人",
            relationship="self",
            role=UserMemberBinding.Role.OWNER,
        )
        self.shared_member = self._create_member(
            owner=self.owner_user,
            name="妈妈",
            relationship="self",
            role=UserMemberBinding.Role.OWNER,
        )
        UserMemberBinding.objects.create(
            user=self.current_user,
            member=self.shared_member,
            relationship="mother",
            role=UserMemberBinding.Role.EDITOR,
            status=UserMemberBinding.Status.ACTIVE,
        )

        today = timezone.localdate()
        self.self_plan = MedicationPlan.objects.create(
            user=self.current_user,
            member=self.self_member,
            drug_name="维生素",
            dose_per_time="1片",
            dose_unit="片",
            frequency_type=MedicationPlan.FrequencyType.DAILY,
            frequency_text="每日一次",
            reminder_times=[{"time": "08:00", "dose": 1}],
            start_date=today,
            reminder_enabled=True,
            status=MedicationPlan.Status.ACTIVE,
        )
        self.authorized_candidate_plan = MedicationPlan.objects.create(
            user=self.owner_user,
            member=self.shared_member,
            drug_name="降压药",
            dose_per_time="1片",
            dose_unit="片",
            frequency_type=MedicationPlan.FrequencyType.DAILY,
            frequency_text="每日一次",
            reminder_times=[{"time": "09:00", "dose": 1}],
            start_date=today,
            reminder_enabled=True,
            status=MedicationPlan.Status.ACTIVE,
        )
        self.unauthorized_plan = MedicationPlan.objects.create(
            user=self.owner_user,
            member=self.shared_member,
            drug_name="止痛药",
            dose_per_time="1片",
            dose_unit="片",
            frequency_type=MedicationPlan.FrequencyType.DAILY,
            frequency_text="每日一次",
            reminder_times=[{"time": "21:00", "dose": 1}],
            start_date=today,
            reminder_enabled=True,
            status=MedicationPlan.Status.ACTIVE,
        )

        scheduled_at = timezone.make_aware(datetime.combine(today, datetime.min.time())) + timedelta(hours=9)
        MedicationRecord.objects.create(
            user=self.owner_user,
            member=self.shared_member,
            plan=self.authorized_candidate_plan,
            scheduled_at=scheduled_at,
            status=MedicationRecord.Status.SCHEDULED,
            planned_dose="1片",
            dose_sequence=1,
            timezone="Asia/Shanghai",
        )
        MedicationRecord.objects.create(
            user=self.owner_user,
            member=self.shared_member,
            plan=self.unauthorized_plan,
            scheduled_at=scheduled_at + timedelta(hours=1),
            status=MedicationRecord.Status.SCHEDULED,
            planned_dose="1片",
            dose_sequence=1,
            timezone="Asia/Shanghai",
        )

    def _create_member(self, *, owner: User, name: str, relationship: str, role: str) -> Member:
        member = Member.objects.create(user=owner, name=name, is_primary=(relationship == "self"))
        UserMemberBinding.objects.create(
            user=owner,
            member=member,
            relationship=relationship,
            role=role,
            status=UserMemberBinding.Status.ACTIVE,
        )
        return member

    def test_enabled_plans_excludes_unauthorized_non_self_plans(self):
        response = self.client.get("/api/v1/medical/medication-reminders/enabled-plans/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        groups = response.json()["data"]["members"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["member"]["id"], self.self_member.id)
        self.assertEqual(groups[0]["source"], "self_member")
        self.assertEqual([plan["id"] for plan in groups[0]["plans"]], [self.self_plan.id])

    def test_put_authorization_includes_only_target_non_self_plan_and_records(self):
        put_response = self.client.put(
            f"/api/v1/medical/medication-reminders/local-authorizations/{self.authorized_candidate_plan.id}/",
            {"enabled": True, "source": "share_cancel_confirm"},
            format="json",
        )
        self.assertEqual(put_response.status_code, status.HTTP_200_OK)
        self.assertTrue(put_response.json()["data"]["enabled"])

        response = self.client.get("/api/v1/medical/medication-reminders/enabled-plans/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        groups = response.json()["data"]["members"]
        self.assertEqual(len(groups), 2)

        shared_group = next(group for group in groups if group["member"]["id"] == self.shared_member.id)
        self.assertEqual(shared_group["source"], "authorized_plan")
        self.assertEqual([plan["id"] for plan in shared_group["plans"]], [self.authorized_candidate_plan.id])
        self.assertEqual([record["plan"] for record in shared_group["records"]], [self.authorized_candidate_plan.id])

    def test_delete_authorization_disables_non_self_plan(self):
        MedicationReminderLocalAuthorization.objects.create(
            user=self.current_user,
            member=self.shared_member,
            medication_plan=self.authorized_candidate_plan,
            enabled=True,
            source="seed",
        )

        delete_response = self.client.delete(
            f"/api/v1/medical/medication-reminders/local-authorizations/{self.authorized_candidate_plan.id}/"
        )
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertFalse(delete_response.json()["data"]["enabled"])

        authorization = MedicationReminderLocalAuthorization.objects.get(
            user=self.current_user,
            medication_plan=self.authorized_candidate_plan,
        )
        self.assertFalse(authorization.enabled)

    def test_put_self_member_plan_does_not_create_redundant_authorization(self):
        response = self.client.put(
            f"/api/v1/medical/medication-reminders/local-authorizations/{self.self_plan.id}/",
            {"enabled": True, "source": "manual"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["data"]["enabled"])
        self.assertFalse(
            MedicationReminderLocalAuthorization.objects.filter(
                user=self.current_user,
                medication_plan=self.self_plan,
            ).exists()
        )
