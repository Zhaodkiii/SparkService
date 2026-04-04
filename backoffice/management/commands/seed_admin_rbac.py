from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from backoffice.models import AdminPermissionPreset, AdminRole, AdminUserRole
from backoffice.rbac import bootstrap_admin_permissions


class Command(BaseCommand):
    help = "Seed default admin RBAC data"

    def handle(self, *args, **options):
        marker, created = AdminPermissionPreset.objects.get_or_create(key="default_rbac_seed_v1")
        if not created:
            self.stdout.write(self.style.WARNING("default RBAC seed already exists"))

        bootstrap_admin_permissions()

        User = get_user_model()
        role = AdminRole.objects.get(code="super_admin")
        linked_count = 0
        for user in User.objects.filter(is_superuser=True):
            _, is_created = AdminUserRole.objects.get_or_create(user=user, role=role)
            if is_created:
                linked_count += 1

        self.stdout.write(self.style.SUCCESS(f"RBAC seeded. linked_superusers={linked_count} marker={marker.key}"))
