from __future__ import annotations

from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    DoctorDepartmentMembership,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalStaffMembership,
)
from hospital_care.services.audit import write_hospital_audit_log

User = get_user_model()


def _lock_hospital(hospital_id) -> Hospital:
    hospital = Hospital.objects.select_for_update().filter(pk=hospital_id).first()
    if hospital is None:
        raise HospitalCareError("HOSPITAL_NOT_FOUND")
    return hospital


def _assert_version(hospital: Hospital, version: int | None):
    if version is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "version"})
    if int(version) != hospital.version:
        raise HospitalCareError("HOSPITAL_VERSION_CONFLICT", details={"version": hospital.version})


def _require_https_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HospitalCareError("REGISTRATION_REDIRECT_INVALID")


def create_hospital(*, request, payload: dict) -> Hospital:
    try:
        hospital = Hospital.objects.create(
            code=payload["code"].strip(),
            name=payload["name"].strip(),
            short_name=(payload.get("short_name") or "").strip(),
            grade=(payload.get("grade") or "").strip(),
            logo_file_id=payload.get("logo_file_id"),
            province_code=(payload.get("province_code") or "").strip(),
            city_code=(payload.get("city_code") or "").strip(),
            district_code=(payload.get("district_code") or "").strip(),
            address=(payload.get("address") or "").strip(),
            service_phone=(payload.get("service_phone") or "").strip(),
            emergency_phone=(payload.get("emergency_phone") or "").strip(),
            website_url=(payload.get("website_url") or "").strip(),
            introduction=payload.get("introduction") or "",
            registration_redirect_url=(payload.get("registration_redirect_url") or "").strip(),
            service_mode=payload.get("service_mode") or Hospital.ServiceMode.DEMO,
            status=Hospital.Status.DRAFT,
        )
    except IntegrityError as exc:
        raise HospitalCareError("HOSPITAL_CODE_CONFLICT") from exc
    write_hospital_audit_log(
        request,
        action="hospital.create",
        resource_type="hospital",
        resource_id=str(hospital.id),
        extra={"hospital_id": str(hospital.id), "code": hospital.code, "name": hospital.name},
    )
    return hospital


def update_hospital(*, request, hospital_id, payload: dict) -> Hospital:
    with transaction.atomic():
        hospital = _lock_hospital(hospital_id)
        _assert_version(hospital, payload.get("version"))
        for field in (
            "name",
            "short_name",
            "grade",
            "province_code",
            "city_code",
            "district_code",
            "address",
            "service_phone",
            "emergency_phone",
            "website_url",
            "introduction",
            "registration_redirect_url",
            "service_mode",
        ):
            if field in payload and payload[field] is not None:
                setattr(hospital, field, payload[field] if field == "introduction" else str(payload[field]).strip())
        if "logo_file_id" in payload:
            hospital.logo_file_id = payload["logo_file_id"]
        hospital.version += 1
        hospital.save()
    write_hospital_audit_log(
        request,
        action="hospital.update",
        resource_type="hospital",
        resource_id=str(hospital.id),
        extra={"hospital_id": str(hospital.id), "version": hospital.version, "status": hospital.status},
    )
    return hospital


def _activation_errors(hospital: Hospital) -> list[str]:
    errors = []
    if not hospital.name.strip() or not hospital.code.strip() or not hospital.address.strip():
        errors.append("基础资料不完整")
    if not hospital.province_code or not hospital.city_code:
        errors.append("行政区划不完整")
    if not HospitalStaffMembership.objects.filter(
        hospital=hospital,
        role=HospitalStaffMembership.Role.HOSPITAL_ADMIN,
        status=HospitalStaffMembership.Status.ACTIVE,
    ).exists():
        errors.append("缺少有效医院管理员")
    if hospital.service_mode == Hospital.ServiceMode.REDIRECT:
        try:
            _require_https_url(hospital.registration_redirect_url)
        except HospitalCareError:
            errors.append("跳转地址未通过可信域校验")
    if hospital.service_mode == Hospital.ServiceMode.INTEGRATED:
        errors.append("HIS 接入尚未配置，不能启用")
    return errors


def activate_hospital(*, request, hospital_id, version: int | None) -> Hospital:
    with transaction.atomic():
        hospital = _lock_hospital(hospital_id)
        _assert_version(hospital, version)
        if hospital.status not in {Hospital.Status.DRAFT, Hospital.Status.SUSPENDED}:
            raise HospitalCareError("HOSPITAL_ACTIVATE_INVALID", details={"status": hospital.status})
        errors = _activation_errors(hospital)
        if errors:
            raise HospitalCareError("HOSPITAL_ACTIVATE_INVALID", details={"checks": errors})
        hospital.status = Hospital.Status.ACTIVE
        hospital.version += 1
        hospital.save(update_fields=["status", "version", "updated_at"])
    write_hospital_audit_log(
        request,
        action="hospital.activate",
        resource_type="hospital",
        resource_id=str(hospital.id),
        extra={"hospital_id": str(hospital.id), "status": hospital.status, "version": hospital.version},
    )
    return hospital


def suspend_hospital(*, request, hospital_id, version: int | None, reason: str) -> Hospital:
    if not (reason or "").strip():
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "reason"})
    with transaction.atomic():
        hospital = _lock_hospital(hospital_id)
        _assert_version(hospital, version)
        if hospital.status != Hospital.Status.ACTIVE:
            raise HospitalCareError("HOSPITAL_ACTIVATE_INVALID", details={"status": hospital.status})
        hospital.status = Hospital.Status.SUSPENDED
        hospital.version += 1
        hospital.save(update_fields=["status", "version", "updated_at"])
    write_hospital_audit_log(
        request,
        action="hospital.suspend",
        resource_type="hospital",
        resource_id=str(hospital.id),
        extra={"hospital_id": str(hospital.id), "status": hospital.status, "reason": reason, "version": hospital.version},
    )
    return hospital


def create_department(*, request, hospital_id, payload: dict) -> HospitalDepartment:
    hospital = Hospital.objects.filter(pk=hospital_id).first()
    if hospital is None:
        raise HospitalCareError("HOSPITAL_NOT_FOUND")
    parent = None
    parent_id = payload.get("parent_id")
    if parent_id:
        parent = HospitalDepartment.objects.filter(pk=parent_id, hospital=hospital).first()
        if parent is None:
            raise HospitalCareError("DEPARTMENT_PARENT_INVALID")
    try:
        department = HospitalDepartment.objects.create(
            hospital=hospital,
            parent=parent,
            code=payload["code"].strip(),
            name=payload["name"].strip(),
            short_name=(payload.get("short_name") or "").strip(),
            description=payload.get("description") or "",
            sort_order=int(payload.get("sort_order") or 0),
            status=payload.get("status") or HospitalDepartment.Status.ACTIVE,
        )
    except IntegrityError as exc:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "code"}) from exc
    write_hospital_audit_log(
        request,
        action="hospital.department.create",
        resource_type="hospital_department",
        resource_id=str(department.id),
        extra={"hospital_id": str(hospital.id), "department_id": str(department.id), "code": department.code},
    )
    return department


def update_department(*, request, department_id, payload: dict) -> HospitalDepartment:
    department = HospitalDepartment.objects.select_related("hospital").filter(pk=department_id).first()
    if department is None:
        raise HospitalCareError("DEPARTMENT_NOT_FOUND")
    parent_id = payload.get("parent_id")
    if "parent_id" in payload:
        if parent_id:
            parent = HospitalDepartment.objects.filter(pk=parent_id, hospital=department.hospital).first()
            if parent is None or parent.id == department.id:
                raise HospitalCareError("DEPARTMENT_PARENT_INVALID")
            department.parent = parent
        else:
            department.parent = None
    for field in ("name", "short_name", "description", "status"):
        if field in payload and payload[field] is not None:
            setattr(department, field, payload[field])
    if "sort_order" in payload and payload["sort_order"] is not None:
        department.sort_order = int(payload["sort_order"])
    department.save()
    write_hospital_audit_log(
        request,
        action="hospital.department.update",
        resource_type="hospital_department",
        resource_id=str(department.id),
        extra={"hospital_id": str(department.hospital_id), "department_id": str(department.id), "status": department.status},
    )
    return department


def grant_staff(*, request, hospital_id, payload: dict) -> HospitalStaffMembership:
    hospital = Hospital.objects.filter(pk=hospital_id).first()
    if hospital is None:
        raise HospitalCareError("HOSPITAL_NOT_FOUND")
    user = User.objects.filter(pk=payload.get("user_id")).first()
    if user is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "user_id"})
    role = payload.get("role")
    if role not in HospitalStaffMembership.Role.values:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "role"})
    try:
        membership = HospitalStaffMembership.objects.create(
            hospital=hospital,
            user=user,
            role=role,
            employee_no=(payload.get("employee_no") or "").strip(),
            status=payload.get("status") or HospitalStaffMembership.Status.INVITED,
            joined_at=timezone.now() if payload.get("status") == HospitalStaffMembership.Status.ACTIVE else None,
        )
    except IntegrityError as exc:
        raise HospitalCareError("STAFF_ALREADY_EXISTS") from exc
    if role == HospitalStaffMembership.Role.DOCTOR:
        DoctorProfile.objects.get_or_create(
            staff_membership=membership,
            defaults={
                "display_name": (payload.get("display_name") or user.get_full_name() or user.username).strip(),
                "title": (payload.get("title") or "").strip(),
                "specialties": payload.get("specialties") or [],
                "introduction": payload.get("introduction") or "",
                "profile_status": DoctorProfile.ProfileStatus.DRAFT,
            },
        )
    write_hospital_audit_log(
        request,
        action="hospital.staff.grant",
        resource_type="hospital_staff",
        resource_id=str(membership.id),
        extra={"hospital_id": str(hospital.id), "user_id": user.id, "role": role, "staff_id": str(membership.id)},
    )
    return membership


def _is_active_hospital_admin(membership: HospitalStaffMembership) -> bool:
    return (
        membership.role == HospitalStaffMembership.Role.HOSPITAL_ADMIN
        and membership.status == HospitalStaffMembership.Status.ACTIVE
    )


def update_staff(*, request, staff_id, payload: dict) -> HospitalStaffMembership:
    membership = HospitalStaffMembership.objects.select_related("hospital", "user").filter(pk=staff_id).first()
    if membership is None:
        raise HospitalCareError("STAFF_NOT_FOUND")
    next_role = payload.get("role") if payload.get("role") is not None else membership.role
    next_status = payload.get("status") if payload.get("status") is not None else membership.status
    if next_role not in HospitalStaffMembership.Role.values:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "role"})
    if next_status not in HospitalStaffMembership.Status.values:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "status"})
    if membership.role == HospitalStaffMembership.Role.DOCTOR and next_role != HospitalStaffMembership.Role.DOCTOR:
        raise HospitalCareError("STAFF_ROLE_LOCKED")
    losing_admin = _is_active_hospital_admin(membership) and (
        next_role != HospitalStaffMembership.Role.HOSPITAL_ADMIN or next_status != HospitalStaffMembership.Status.ACTIVE
    )
    if losing_admin and membership.hospital.status == Hospital.Status.ACTIVE:
        has_other_admin = (
            HospitalStaffMembership.objects.filter(
                hospital=membership.hospital,
                role=HospitalStaffMembership.Role.HOSPITAL_ADMIN,
                status=HospitalStaffMembership.Status.ACTIVE,
            )
            .exclude(pk=membership.pk)
            .exists()
        )
        if not has_other_admin:
            raise HospitalCareError("STAFF_LAST_ADMIN")
    with transaction.atomic():
        if "employee_no" in payload:
            membership.employee_no = (payload.get("employee_no") or "").strip()
        membership.role = next_role
        membership.status = next_status
        if next_status == HospitalStaffMembership.Status.ACTIVE and membership.joined_at is None:
            membership.joined_at = timezone.now()
        membership.save()
        if next_role == HospitalStaffMembership.Role.DOCTOR:
            DoctorProfile.objects.get_or_create(
                staff_membership=membership,
                defaults={
                    "display_name": (payload.get("display_name") or membership.user.get_full_name() or membership.user.username).strip(),
                    "title": (payload.get("title") or "").strip(),
                    "profile_status": DoctorProfile.ProfileStatus.DRAFT,
                },
            )
    write_hospital_audit_log(
        request,
        action="hospital.staff.update",
        resource_type="hospital_staff",
        resource_id=str(membership.id),
        extra={
            "hospital_id": str(membership.hospital_id),
            "staff_id": str(membership.id),
            "role": membership.role,
            "status": membership.status,
        },
    )
    return membership


def update_doctor(*, request, doctor_id, payload: dict) -> DoctorProfile:
    doctor = DoctorProfile.objects.select_related("staff_membership", "staff_membership__hospital").filter(pk=doctor_id).first()
    if doctor is None:
        raise HospitalCareError("DOCTOR_PROFILE_NOT_ACTIVE")
    for field in ("display_name", "title", "introduction", "license_status", "profile_status"):
        if field in payload and payload[field] is not None:
            setattr(doctor, field, payload[field])
    if "specialties" in payload and payload["specialties"] is not None:
        doctor.specialties = payload["specialties"]
    if "avatar_file_id" in payload:
        doctor.avatar_file_id = payload["avatar_file_id"]
    doctor.save()
    department_id = payload.get("primary_department_id")
    if department_id:
        department = HospitalDepartment.objects.filter(pk=department_id, hospital_id=doctor.staff_membership.hospital_id).first()
        if department is None:
            raise HospitalCareError("DEPARTMENT_NOT_FOUND")
        DoctorDepartmentMembership.objects.filter(doctor=doctor, is_primary=True).update(is_primary=False)
        membership, _ = DoctorDepartmentMembership.objects.get_or_create(
            doctor=doctor,
            department=department,
            defaults={"is_primary": True},
        )
        if not membership.is_primary:
            membership.is_primary = True
            membership.save(update_fields=["is_primary"])
    write_hospital_audit_log(
        request,
        action="hospital.doctor.update",
        resource_type="doctor",
        resource_id=str(doctor.id),
        extra={"hospital_id": str(doctor.staff_membership.hospital_id), "doctor_id": str(doctor.id)},
    )
    return doctor
