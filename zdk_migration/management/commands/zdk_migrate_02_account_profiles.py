from django.contrib.auth import get_user_model

from accounts.models import AccountProfile

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all


class Command(ZdkMigrateCommand):
    help = "Migrate user_profile -> accounts_accountprofile"

    def run_migration(self) -> None:
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT id, user_id
            FROM user_profile
            ORDER BY user_id, id DESC
            """
        )
        seen_users: set[int] = set()
        self.stdout.write(f"Found {len(rows)} legacy profiles")
        for row in rows:
            user_id = row["user_id"]
            if user_id in seen_users:
                self.stats.skipped += 1
                continue
            seen_users.add(user_id)
            if not User.objects.filter(pk=user_id).exists():
                self.log_skip(f"profile user missing user_id={user_id}")
                continue

            profile_exists = AccountProfile.objects.filter(user_id=user_id).exists()
            if profile_exists:
                self.stats.skipped += 1
                continue
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(user_id=user_id):
                AccountProfile.objects.get_or_create(user_id=user_id)

            self.run_safe(f"profile:{user_id}", _create)
            if AccountProfile.objects.filter(user_id=user_id).exists():
                self.stats.migrated += 1
