from django.core.management import call_command
from django.test import TestCase

from hospital_care.data.tianchang_public_staff import doctors_with_departments
from hospital_care.models import Hospital, HospitalStaffMembership


class TianchangPublicStaffTests(TestCase):
    def test_public_doctors_map_to_known_departments(self):
        items = doctors_with_departments()
        self.assertGreaterEqual(len(items), 40)
        codes = {item["department_code"] for item in items}
        self.assertIn("SP", codes)
        self.assertIn("ORTH", codes)
        self.assertIn("OBG", codes)
        self.assertIn("ONCO", codes)

    def test_seed_command_creates_active_hospital_admin(self):
        call_command("seed_tianchang_hospital", code="000001", activate=True)
        hospital = Hospital.objects.get(code="000001")
        self.assertEqual(hospital.name, "天长市中医院")
        self.assertEqual(hospital.status, Hospital.Status.ACTIVE)
        self.assertTrue(
            HospitalStaffMembership.objects.filter(
                hospital=hospital,
                role=HospitalStaffMembership.Role.HOSPITAL_ADMIN,
                status=HospitalStaffMembership.Status.ACTIVE,
                user__username="tcszyy_admin",
            ).exists()
        )
        self.assertGreaterEqual(hospital.departments.count(), 20)
        self.assertGreaterEqual(
            HospitalStaffMembership.objects.filter(hospital=hospital, role=HospitalStaffMembership.Role.DOCTOR).count(),
            40,
        )
