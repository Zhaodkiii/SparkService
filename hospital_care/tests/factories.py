from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.utils import timezone

from ai_config.models import AIModelCatalog, AIProviderKeyConfig, AIScenarioModelBinding, IdentityKind, ScenarioKey
from medical.models import Member, UserMemberBinding

from hospital_care.models import (
    ClinicalAgentProfile,
    DoctorDepartmentMembership,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalStaffMembership,
)

User = get_user_model()


class DummyRequest:
    def __init__(self, user, data=None, path="/api/test", method="POST"):
        self.user = user
        self.data = data or {}
        self.path = path
        self.method = method
        self.request_id = "req_test"
        self.META = {}
        self.headers = {}


def make_user(username: str, **kwargs):
    return User.objects.create_user(username=username, email=f"{username}@test.invalid", **kwargs)


def make_member(user, name="演示患者"):
    member = Member.objects.create(user=user, name=name, is_primary=True)
    UserMemberBinding.objects.create(user=user, member=member, relationship="self", role=UserMemberBinding.Role.OWNER)
    return member


def make_hospital(**kwargs) -> Hospital:
    defaults = {
        "code": kwargs.pop("code", f"H-{timezone.now().timestamp()}"),
        "name": "测试医院",
        "address": "测试路 1 号",
        "province_code": "340000",
        "city_code": "341100",
        "service_mode": Hospital.ServiceMode.DEMO,
        "status": Hospital.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Hospital.objects.create(**defaults)


def make_department(hospital, code="CARD", name="心内科") -> HospitalDepartment:
    return HospitalDepartment.objects.create(hospital=hospital, code=code, name=name, status=HospitalDepartment.Status.ACTIVE)


def make_staff(hospital, user, role=HospitalStaffMembership.Role.DOCTOR, status=HospitalStaffMembership.Status.ACTIVE) -> HospitalStaffMembership:
    return HospitalStaffMembership.objects.create(
        hospital=hospital,
        user=user,
        role=role,
        status=status,
        joined_at=timezone.now(),
        employee_no=f"E{user.id}",
    )


def make_doctor(hospital, user=None, department=None, display_name="张医生") -> DoctorProfile:
    user = user or make_user(f"doc-{display_name}-{hospital.code}")
    membership = make_staff(hospital, user, HospitalStaffMembership.Role.DOCTOR)
    doctor = DoctorProfile.objects.create(
        staff_membership=membership,
        display_name=display_name,
        title="主任医师",
        specialties=["心内科"],
        introduction="测试医生",
        license_status=DoctorProfile.LicenseStatus.VERIFIED,
        profile_status=DoctorProfile.ProfileStatus.ACTIVE,
    )
    if department:
        DoctorDepartmentMembership.objects.create(doctor=doctor, department=department, is_primary=True)
    return doctor


def make_provider(company="test", *, name="test-provider") -> AIProviderKeyConfig:
    return AIProviderKeyConfig.objects.create(
        kind=AIProviderKeyConfig.Kind.API,
        name=name,
        company=company,
        key="sk-test",
        request_url="https://example.test/v1/chat/completions",
        is_active=True,
        is_using=True,
    )


def make_scenario_binding(*, model_name="hospital-care-test-model", company="test") -> AIScenarioModelBinding:
    model, _ = AIModelCatalog.objects.get_or_create(
        name=model_name,
        defaults={"display_name": "Test Model", "company": company, "is_active": True},
    )
    if not model.is_active:
        model.is_active = True
        model.save(update_fields=["is_active"])
    return AIScenarioModelBinding.objects.create(
        scenario=ScenarioKey.CHAT,
        identity=IdentityKind.AGENT,
        model=model,
        display_name="测试智能体绑定",
        is_active=True,
        is_default=False,
    )


def make_embedding_binding(*, model_name="hospital-embed-test", company="test") -> AIScenarioModelBinding:
    model, _ = AIModelCatalog.objects.get_or_create(
        name=model_name,
        defaults={"display_name": "Test Embedding", "company": company, "is_active": True},
    )
    return AIScenarioModelBinding.objects.create(
        scenario=ScenarioKey.EMBEDDING,
        identity=IdentityKind.MODEL,
        model=model,
        display_name="测试 Embedding",
        is_active=True,
        is_default=False,
    )


def make_agent(hospital, doctor, department, *, status=ClinicalAgentProfile.PublicationStatus.PUBLISHED, scenario=None) -> ClinicalAgentProfile:
    return ClinicalAgentProfile.objects.create(
        hospital=hospital,
        doctor=doctor,
        department=department,
        scenario_binding=scenario or make_scenario_binding(),
        name=f"{doctor.display_name} AI 助手",
        public_summary="测试智能体",
        greeting="您好",
        service_boundary="健康信息与就医指导，不提供确诊。",
        publication_status=status,
        published_at=timezone.now() if status == ClinicalAgentProfile.PublicationStatus.PUBLISHED else None,
    )
