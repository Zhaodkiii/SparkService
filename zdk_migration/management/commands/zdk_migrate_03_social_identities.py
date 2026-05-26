from django.contrib.auth import get_user_model

from accounts.models import SocialIdentity
from accounts.services.phone_number_service import PhoneNumberService
from common.exceptions import APIError

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.error_log import record_migration_issue
from zdk_migration.lib.old_db import old_fetch_all


ALLOWED = {"apple", "google", "phone", "otp"}


class Command(ZdkMigrateCommand):
    help = "Migrate auth_identity -> accounts_socialidentity"

    def run_migration(self) -> None:
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT id, user_id, bundle_id, provider, provider_uid
            FROM auth_identity
            WHERE provider IN ('apple', 'google', 'phone', 'otp')
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} social identities")
        duplicate_ids: list[int] = []
        unsupported_ids: list[int] = []
        for row in rows:
            provider = (row.get("provider") or "").strip()
            if provider not in ALLOWED:
                unsupported_ids.append(row["id"])
                self.stats.skipped += 1
                continue
            if not User.objects.filter(pk=row["user_id"]).exists():
                self.log_skip(f"identity user missing id={row['user_id']}")
                continue
            bundle_id = (row.get("bundle_id") or "")[:128]
            provider_uid = row.get("provider_uid") or ""
            if provider in {"phone", "otp"}:
                provider = SocialIdentity.Provider.PHONE
                try:
                    provider_uid = PhoneNumberService.normalize_e164(provider_uid)
                except APIError:
                    self.log_skip(f"identity phone invalid id={row['id']} provider_uid={provider_uid}")
                    continue
            if SocialIdentity.objects.filter(
                bundle_id=bundle_id, provider=provider, provider_uid=provider_uid
            ).exists():
                duplicate_ids.append(row["id"])
                self.stats.skipped += 1
                continue
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, bundle_id=bundle_id, provider=provider, provider_uid=provider_uid):
                SocialIdentity.objects.create(
                    user_id=row["user_id"],
                    provider=provider,
                    provider_uid=provider_uid,
                    bundle_id=bundle_id,
                )

            self.run_safe(f"identity:{row['id']}", _create)
            self.stats.migrated += 1

        if duplicate_ids and self.stats.migrated > 0:
            record_migration_issue(
                self.command_name,
                "SKIP",
                f"identity duplicate legacy_ids={','.join(str(item) for item in duplicate_ids)}",
                sample_limit=0,
            )
        elif duplicate_ids:
            record_migration_issue(
                self.command_name,
                "SKIP",
                f"identity duplicate existing_count={len(duplicate_ids)}",
                sample_limit=0,
            )
        if unsupported_ids:
            record_migration_issue(
                self.command_name,
                "SKIP",
                f"identity unsupported provider legacy_ids={','.join(str(item) for item in unsupported_ids)}",
                sample_limit=0,
            )
