from rest_framework.permissions import BasePermission


class AdminOnlyPermission(BasePermission):
    """
    Minimal RBAC guard: staff or superuser only.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))

