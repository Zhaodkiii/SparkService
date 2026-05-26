from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all


class Command(ZdkMigrateCommand):
    help = "Migrate auth_user from ZhaodkDream (preserve primary keys)"

    def run_migration(self) -> None:
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT id, username, email, password, first_name, last_name,
                   is_staff, is_active, is_superuser, date_joined, last_login
            FROM auth_user
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} legacy users")
        for row in rows:
            uid = row["id"]
            if User.objects.filter(pk=uid).exists():
                self.stats.skipped += 1
                continue

            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, uid=uid):
                User.objects.create(
                    id=uid,
                    username=row["username"] or f"user_{uid}",
                    email=row.get("email") or "",
                    password=row["password"],
                    first_name=row.get("first_name") or "",
                    last_name=row.get("last_name") or "",
                    is_staff=bool(row.get("is_staff")),
                    is_active=bool(row.get("is_active", True)),
                    is_superuser=bool(row.get("is_superuser")),
                    date_joined=row.get("date_joined") or parse_datetime("1970-01-01T00:00:00Z"),
                    last_login=row.get("last_login"),
                )

            self.run_safe(f"user:{uid}", _create)
            if User.objects.filter(pk=uid).exists():
                self.stats.migrated += 1
