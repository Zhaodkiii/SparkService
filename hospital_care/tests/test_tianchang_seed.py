from django.core.management import call_command
from django.test import TestCase

from hospital_care.data.tianchang_public_staff import doctors_with_departments
from hospital_care.models import (
    ClinicalAgentProfile,
    DoctorDepartmentMembership,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalStaffMembership,
)
from hospital_care.tests.factories import make_scenario_binding


class TianchangPublicStaffTests(TestCase):
    def test_public_doctors_map_to_known_departments(self):
        items = doctors_with_departments()
        self.assertEqual(len(items), 142)
        codes = {item["department_code"] for item in items}
        self.assertIn("CLIN_SURG", codes)
        self.assertIn("CLIN_ORTH_NS", codes)
        self.assertIn("CLIN_OBGYN", codes)
        self.assertIn("CLIN_ONCO", codes)
        self.assertTrue(all(item["avatar_url"] for item in items))
        self.assertEqual(sum(len(item["department_codes"]) for item in items), 145)

    def test_seed_command_creates_active_hospital_admin(self):
        make_scenario_binding(model_name="tianchang-seed-test-model")
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
        self.assertEqual(hospital.departments.count(), 30)
        self.assertEqual(
            HospitalStaffMembership.objects.filter(
                hospital=hospital,
                role=HospitalStaffMembership.Role.DOCTOR,
            ).count(),
            142,
        )
        doctors = DoctorProfile.objects.filter(staff_membership__hospital=hospital)
        agents = ClinicalAgentProfile.objects.filter(hospital=hospital)
        self.assertEqual(doctors.count(), 142)
        self.assertEqual(
            DoctorDepartmentMembership.objects.filter(doctor__in=doctors).count(),
            145,
        )
        self.assertEqual(
            HospitalDepartment.objects.filter(hospital=hospital, parent__isnull=True).count(),
            2,
        )
        self.assertEqual(agents.count(), 142)
        self.assertEqual(
            agents.filter(
                publication_status=ClinicalAgentProfile.PublicationStatus.PUBLISHED,
                avatar_source=ClinicalAgentProfile.AvatarSource.DOCTOR,
                avatar_file__isnull=True,
            ).count(),
            142,
        )
        self.assertFalse(doctors.filter(avatar_file__isnull=True).exists())
