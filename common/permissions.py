from rest_framework.permissions import BasePermission
from backoffice.rbac import has_permission_code


class AdminOnlyPermission(BasePermission):
    """
    Minimal RBAC guard: staff or superuser only.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


class AdminCodePermission(AdminOnlyPermission):
    """
    Fine-grained RBAC on top of staff/superuser gate.
    View should define `required_permission_code`.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if getattr(request.user, "is_superuser", False):
            return True
        required_code = getattr(view, "required_permission_code", "") or ""
        return has_permission_code(request.user.id, required_code)
