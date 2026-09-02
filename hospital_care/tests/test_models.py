from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from hospital_care.models import DoctorDepartmentMembership, DoctorProfile, HospitalDepartment, HospitalStaffMembership
from hospital_care.tests.factories import make_department, make_doctor, make_hospital, make_staff, make_user


class OrganizationConstraintTests(TestCase):
    def test_hospital_code_unique(self):
        make_hospital(code="UNIQ-1")
        with self.assertRaises(IntegrityError):
            make_hospital(code="UNIQ-1")

    def test_department_code_unique_per_hospital(self):
        hospital = make_hospital(code="D-1")
        make_department(hospital, code="CARD")
        with self.assertRaises(IntegrityError):
            make_department(hospital, code="CARD")

    def test_parent_department_must_be_same_hospital(self):
        hospital_a = make_hospital(code="PA")
        hospital_b = make_hospital(code="PB")
        parent = make_department(hospital_a, code="P")
        child = HospitalDepartment(hospital=hospital_b, parent=parent, code="C", name="子科室")
        with self.assertRaises(ValidationError):
            child.clean()

    def test_staff_unique_per_hospital_user(self):
        hospital = make_hospital(code="S-1")
        user = make_user("staff-dup")
        make_staff(hospital, user, HospitalStaffMembership.Role.HOSPITAL_ADMIN)
        with self.assertRaises(IntegrityError):
            make_staff(hospital, user, HospitalStaffMembership.Role.DOCTOR)

    def test_doctor_profile_requires_doctor_role(self):
        hospital = make_hospital(code="S-2")
        user = make_user("admin-no-doc")
        membership = make_staff(hospital, user, HospitalStaffMembership.Role.HOSPITAL_ADMIN)
        profile = DoctorProfile(staff_membership=membership, display_name="错误")
        with self.assertRaises(ValidationError):
            profile.clean()

    def test_doctor_department_must_match_hospital(self):
        hospital_a = make_hospital(code="DA")
        hospital_b = make_hospital(code="DB")
        doctor = make_doctor(hospital_a)
        foreign_dept = make_department(hospital_b, code="X")
        membership = DoctorDepartmentMembership(doctor=doctor, department=foreign_dept, is_primary=True)
        with self.assertRaises(ValidationError):
            membership.clean()

    def test_doctor_department_unique(self):
        hospital = make_hospital(code="DD")
        department = make_department(hospital)
        doctor = make_doctor(hospital, department=department)
        with self.assertRaises(IntegrityError):
            DoctorDepartmentMembership.objects.create(doctor=doctor, department=department)
