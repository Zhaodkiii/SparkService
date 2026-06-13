from django.conf import settings
from django.db import models


class AdminRole(models.Model):
    name = models.CharField(max_length=64, unique=True)
    code = models.CharField(max_length=64, unique=True, db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return f"{self.name}({self.code})"


class AdminPermission(models.Model):
    class PermissionType(models.TextChoices):
        MENU = "menu"
        BUTTON = "button"
        API = "api"

    name = models.CharField(max_length=128)
    code = models.CharField(max_length=128, unique=True, db_index=True)
    permission_type = models.CharField(max_length=16, choices=PermissionType.choices, db_index=True)
    path = models.CharField(max_length=255, blank=True, default="")
    method = models.CharField(max_length=16, blank=True, default="")
    parent_code = models.CharField(max_length=128, blank=True, default="", db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["permission_type", "code", "id"]

    def __str__(self):
        return f"{self.code}"


class AdminRolePermission(models.Model):
    role = models.ForeignKey(AdminRole, related_name="role_permissions", on_delete=models.CASCADE)
    permission = models.ForeignKey(AdminPermission, related_name="permission_roles", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uniq_admin_role_permission"),
        ]


class AdminUserRole(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="admin_user_roles", on_delete=models.CASCADE)
    role = models.ForeignKey(AdminRole, related_name="role_users", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uniq_admin_user_role"),
        ]


class AdminAuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=128, db_index=True)
    resource_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    resource_id = models.CharField(max_length=64, blank=True, default="")
    method = models.CharField(max_length=16, blank=True, default="")
    path = models.CharField(max_length=255, blank=True, default="", db_index=True)
    status_code = models.IntegerField(default=0, db_index=True)
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ip_address = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.TextField(blank=True, default="")
    request_payload = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class AdminPermissionPreset(models.Model):
    """
    Seed marker table for idempotent RBAC bootstrap.
    """

    key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.key


class MedicalDataMemberStats(models.Model):
    """成员维度医疗数据预聚合统计（BACKOFFICE-MED-000001）。"""

    class RefreshStatus(models.TextChoices):
        READY = "ready", "ready"
        REFRESHING = "refreshing", "refreshing"
        STALE = "stale", "stale"

    member = models.OneToOneField(
        "medical.Member",
        related_name="admin_medical_stats",
        on_delete=models.CASCADE,
        db_index=True,
    )
    medical_case_count = models.PositiveIntegerField(default=0)
    health_exam_report_count = models.PositiveIntegerField(default=0)
    examination_report_count = models.PositiveIntegerField(default=0)
    medicine_box_count = models.PositiveIntegerField(default=0)
    prescription_count = models.PositiveIntegerField(default=0)
    medication_plan_count = models.PositiveIntegerField(default=0)
    symptom_count = models.PositiveIntegerField(default=0)
    visit_count = models.PositiveIntegerField(default=0)
    surgery_count = models.PositiveIntegerField(default=0)
    follow_up_count = models.PositiveIntegerField(default=0)
    attachment_count = models.PositiveIntegerField(default=0)
    total_count = models.PositiveIntegerField(default=0, db_index=True)
    ai_recognition_count = models.PositiveIntegerField(default=0)
    ai_pending_count = models.PositiveIntegerField(default=0)
    manual_source_count = models.PositiveIntegerField(default=0)
    quality_flag_count = models.PositiveIntegerField(default=0)
    today_medication_total = models.PositiveIntegerField(default=0)
    today_medication_taken = models.PositiveIntegerField(default=0)
    today_medication_skipped = models.PositiveIntegerField(default=0)
    adherence_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    last_medical_updated_at = models.DateTimeField(null=True, blank=True, db_index=True)
    refresh_status = models.CharField(
        max_length=16,
        choices=RefreshStatus.choices,
        default=RefreshStatus.READY,
        db_index=True,
    )
    refreshed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "backoffice_medical_data_member_stats"
        indexes = [
            models.Index(
                fields=["total_count", "last_medical_updated_at"],
                name="backoffice__total_c_4b9c95_idx",
            ),
            models.Index(
                fields=["refresh_status", "refreshed_at"],
                name="backoffice__refresh_3b38b2_idx",
            ),
        ]


class MedicalDataUserStats(models.Model):
    """用户维度医疗数据预聚合统计（BACKOFFICE-MED-000001）。"""

    class RefreshStatus(models.TextChoices):
        READY = "ready", "ready"
        REFRESHING = "refreshing", "refreshing"
        STALE = "stale", "stale"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="medical_data_stats",
        on_delete=models.CASCADE,
        db_index=True,
    )
    member_count = models.PositiveIntegerField(default=0)
    members_with_data_count = models.PositiveIntegerField(default=0, db_index=True)
    medical_data_total = models.PositiveIntegerField(default=0, db_index=True)
    attachment_count = models.PositiveIntegerField(default=0, db_index=True)
    ai_task_count = models.PositiveIntegerField(default=0, db_index=True)
    quality_flag_count = models.PositiveIntegerField(default=0)
    category_totals = models.JSONField(default=dict, blank=True)
    last_medical_updated_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_source = models.CharField(max_length=32, blank=True, default="")
    refresh_status = models.CharField(
        max_length=16,
        choices=RefreshStatus.choices,
        default=RefreshStatus.READY,
        db_index=True,
    )
    refreshed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "backoffice_medical_data_user_stats"
        indexes = [
            models.Index(
                fields=["-last_medical_updated_at", "user_id"],
                name="backoffice__last_me_111335_idx",
            ),
            models.Index(
                fields=["-medical_data_total", "user_id"],
                name="backoffice__medical_be0779_idx",
            ),
        ]


class MedicalDataGlobalStatsSnapshot(models.Model):
    """全局医疗数据统计快照。"""

    class RefreshStatus(models.TextChoices):
        READY = "ready", "ready"
        REFRESHING = "refreshing", "refreshing"
        STALE = "stale", "stale"

    key = models.CharField(max_length=32, unique=True, default="global")
    users_with_medical_data = models.PositiveIntegerField(default=0)
    users_with_ai_recognition = models.PositiveIntegerField(default=0)
    medical_data_total = models.PositiveIntegerField(default=0)
    attachment_total = models.PositiveIntegerField(default=0)
    refresh_status = models.CharField(
        max_length=16,
        choices=RefreshStatus.choices,
        default=RefreshStatus.READY,
    )
    refreshed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "backoffice_medical_data_global_stats"
