from rest_framework.permissions import BasePermission

from common.permissions import AdminCodePermission
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalConversationBinding, HospitalStaffMembership
from hospital_care.selectors.doctor_workspace import get_active_doctor, get_active_membership
from medical.services.member_binding_service import get_active_binding


class HospitalPatientPermission(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if isinstance(obj, ClinicalConversationBinding):
            if obj.thread.user_id != request.user.id:
                return False
            member_id = obj.thread.member_id
            if member_id is None:
                return True
            return get_active_binding(user=request.user, member_id=member_id) is not None
        return False


class HospitalStaffPermission(BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        try:
            request.hospital_membership = get_active_membership(user=request.user)
        except HospitalCareError:
            return False
        return True


class DoctorConversationPermission(BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        try:
            request.hospital_doctor = get_active_doctor(user=request.user)
        except HospitalCareError:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        doctor = getattr(request, "hospital_doctor", None)
        if doctor is None or not isinstance(obj, ClinicalConversationBinding):
            return False
        return obj.doctor_id == doctor.id and obj.hospital_id == doctor.staff_membership.hospital_id


class HospitalAdminPermission(BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        try:
            membership = get_active_membership(user=request.user)
        except HospitalCareError:
            return False
        if membership.role != HospitalStaffMembership.Role.HOSPITAL_ADMIN:
            return False
        request.hospital_membership = membership
        return True


class BackofficeHospitalPermission(AdminCodePermission):
    pass
