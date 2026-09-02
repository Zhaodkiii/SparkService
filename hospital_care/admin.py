from django.contrib import admin

from hospital_care.models import (
    ChatMessageAttribution,
    ClinicalAgentKnowledgeBinding,
    ClinicalAgentProfile,
    ClinicalConversationBinding,
    DoctorDepartmentMembership,
    DoctorProfile,
    Hospital,
    HospitalCareCommandReceipt,
    HospitalDepartment,
    HospitalStaffMembership,
)


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "status", "service_mode", "updated_at")
    search_fields = ("name", "code")
    list_filter = ("status", "service_mode")
    readonly_fields = ("version", "created_at", "updated_at")


@admin.register(HospitalDepartment)
class HospitalDepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "hospital", "status", "sort_order")
    list_filter = ("status",)
    search_fields = ("name", "code")


@admin.register(HospitalStaffMembership)
class HospitalStaffMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "hospital", "role", "status", "employee_no")
    list_filter = ("role", "status")


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "title", "profile_status", "license_status")
    list_filter = ("profile_status", "license_status")


admin.site.register(DoctorDepartmentMembership)
admin.site.register(ClinicalAgentProfile)
admin.site.register(ClinicalAgentKnowledgeBinding)
admin.site.register(ClinicalConversationBinding)
admin.site.register(ChatMessageAttribution)
admin.site.register(HospitalCareCommandReceipt)
