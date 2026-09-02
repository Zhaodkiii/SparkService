from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hospital_care.data.tianchang_public_staff import DEPARTMENTS, doctors_with_departments
from hospital_care.models import (
    DoctorDepartmentMembership,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalStaffMembership,
)

User = get_user_model()

DEFAULT_CODE = "000001"
DEFAULT_PASSWORD = "tcszyy-demo"
ADMIN_USERNAME = "tcszyy_admin"

HOSPITAL_DEFAULTS = {
    "name": "天长市中医院",
    "short_name": "天长中医院",
    "grade": "三级中医医院",
    "province_code": "340000",
    "city_code": "341100",
    "district_code": "341181",
    "address": "安徽省滁州市天长市天宁大道 222 号（新院区）",
    "service_phone": "0550-7021777",
    "emergency_phone": "0550-7042259",
    "website_url": "http://www.tcszyy.com/",
    "service_mode": Hospital.ServiceMode.DEMO,
    "introduction": (
        "天长市中医院始建于1954年，为全国示范中医院、三级中医医院。"
        "开设30多个临床医技科室，职工与医生资料取自医院官网公开专家名录，仅用于产品演示。"
    ),
}


class Command(BaseCommand):
    help = "为天长市中医院（默认 code=000001）写入公开科室、医院管理员和官网专家名录。"

    def add_arguments(self, parser):
        parser.add_argument("--code", default=DEFAULT_CODE, help="医院唯一编码，默认 000001")
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help="演示账号密码")
        parser.add_argument("--activate", action="store_true", help="管理员写入后把医院标为已启用")

    def handle(self, *args, **options):
        code = (options["code"] or DEFAULT_CODE).strip()
        password = options["password"]
        with transaction.atomic():
            hospital = self._hospital(code)
            departments = self._departments(hospital)
            admin = self._user(ADMIN_USERNAME, first_name="医院管理员", password=password, is_staff=True)
            self._membership(
                hospital,
                admin,
                HospitalStaffMembership.Role.HOSPITAL_ADMIN,
                employee_no="A0001",
            )
            doctor_count = 0
            for index, item in enumerate(doctors_with_departments(), start=1):
                username = f"tcszyy_{index:03d}"
                user = self._user(username, first_name=item["name"], password=password)
                membership = self._membership(
                    hospital,
                    user,
                    HospitalStaffMembership.Role.DOCTOR,
                    employee_no=f"D{index:04d}",
                )
                doctor = self._doctor(membership, item)
                department = departments[item["department_code"]]
                DoctorDepartmentMembership.objects.get_or_create(
                    doctor=doctor,
                    department=department,
                    defaults={"is_primary": True},
                )
                doctor_count += 1
            if options["activate"] and hospital.status != Hospital.Status.ACTIVE:
                hospital.status = Hospital.Status.ACTIVE
                hospital.version += 1
                hospital.save(update_fields=["status", "version", "updated_at"])
        self.stdout.write(self.style.SUCCESS(
            f"医院 {hospital.name}({hospital.code}) 已写入：科室 {len(departments)}，"
            f"管理员 {ADMIN_USERNAME}，医生 {doctor_count}。演示密码 {password}"
        ))
        self.stdout.write(
            "后台添加管理员：医院详情 → 职工与医生 → 邀请职工 → 搜索账号并选择「医院管理员」+「有效」。"
        )

    def _hospital(self, code: str) -> Hospital:
        hospital, created = Hospital.objects.get_or_create(code=code, defaults=HOSPITAL_DEFAULTS)
        dirty = []
        for field, value in HOSPITAL_DEFAULTS.items():
            if not getattr(hospital, field):
                setattr(hospital, field, value)
                dirty.append(field)
        if dirty:
            hospital.save(update_fields=[*dirty, "updated_at"])
        if created:
            self.stdout.write(f"已创建医院 {code}")
        else:
            self.stdout.write(f"已使用现有医院 {code} / {hospital.name}")
        return hospital

    def _departments(self, hospital: Hospital) -> dict[str, HospitalDepartment]:
        result = {}
        for index, (code, name, short_name, description) in enumerate(DEPARTMENTS):
            department, _ = HospitalDepartment.objects.get_or_create(
                hospital=hospital,
                code=code,
                defaults={
                    "name": name,
                    "short_name": short_name,
                    "description": description,
                    "sort_order": index,
                    "status": HospitalDepartment.Status.ACTIVE,
                },
            )
            result[code] = department
        return result

    def _user(self, username: str, first_name: str, password: str, is_staff: bool = False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@tcszyy.demo", "first_name": first_name, "is_staff": is_staff},
        )
        if created or not user.has_usable_password():
            user.set_password(password)
        if user.first_name != first_name:
            user.first_name = first_name
        if is_staff and not user.is_staff:
            user.is_staff = True
        user.save()
        return user

    def _membership(self, hospital, user, role, employee_no: str):
        membership, created = HospitalStaffMembership.objects.get_or_create(
            hospital=hospital,
            user=user,
            defaults={
                "role": role,
                "status": HospitalStaffMembership.Status.ACTIVE,
                "joined_at": timezone.now(),
                "employee_no": employee_no,
            },
        )
        if not created and membership.status != HospitalStaffMembership.Status.ACTIVE:
            membership.status = HospitalStaffMembership.Status.ACTIVE
            membership.role = role
            membership.joined_at = membership.joined_at or timezone.now()
            membership.employee_no = membership.employee_no or employee_no
            membership.save()
        return membership

    def _doctor(self, membership, item: dict) -> DoctorProfile:
        doctor, created = DoctorProfile.objects.get_or_create(
            staff_membership=membership,
            defaults={
                "display_name": item["name"],
                "title": item["title"],
                "specialties": [item["department_code"]],
                "introduction": f"{item['introduction']}（来源：医院官网公开专家名录，诊室 {item['room']}）",
                "license_status": DoctorProfile.LicenseStatus.VERIFIED,
                "profile_status": DoctorProfile.ProfileStatus.ACTIVE,
            },
        )
        if not created and doctor.profile_status != DoctorProfile.ProfileStatus.ACTIVE:
            doctor.profile_status = DoctorProfile.ProfileStatus.ACTIVE
            doctor.license_status = DoctorProfile.LicenseStatus.VERIFIED
            doctor.save(update_fields=["profile_status", "license_status", "updated_at"])
        return doctor
