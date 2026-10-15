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
