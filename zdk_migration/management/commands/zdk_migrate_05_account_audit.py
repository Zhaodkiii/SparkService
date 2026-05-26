from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime

from accounts.models import AccountDeactivation, AccountDeactivationAudit, LoginAudit

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all, old_table_exists
from zdk_migration.lib.transforms import aware_datetime, deactivation_audit_action, deactivation_state, login_outcome, login_provider_to_new


class Command(ZdkMigrateCommand):
    help = "Migrate login_audit and account deactivation records"

    def run_migration(self) -> None:
        self._migrate_login_audit()
        self._migrate_deactivations()

    def _migrate_login_audit(self) -> None:
        if not old_table_exists("login_audit"):
            return
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT id, user_id, provider, audience, bundle_id, device_id, ip, user_agent,
                   success, error, raw_claims, created_at
            FROM login_audit
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} login audit rows")
        deact_map: dict[int, int] = {}
        for row in rows:
            provider = login_provider_to_new(row.get("provider"))
            if not provider:
                self.stats.skipped += 1
                continue
            user_id = row.get("user_id")
            if user_id and not User.objects.filter(pk=user_id).exists():
                user_id = None
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, provider=provider, user_id=user_id):
                LoginAudit.objects.create(
                    user_id=user_id,
                    provider=provider,
                    outcome=login_outcome(row.get("success")),
                    ip_address=str(row.get("ip") or "")[:64],
                    user_agent=row.get("user_agent") or "",
                    bundle_id=(row.get("bundle_id") or row.get("audience") or "")[:128],
                    device_id=(row.get("device_id") or "")[:128],
                    raw_claims=row.get("raw_claims"),
                    request_id="",
                )

            self.run_safe(f"login_audit:{row['id']}", _create)
            self.stats.migrated += 1

    def _migrate_deactivations(self) -> None:
        if not old_table_exists("account_deactivation"):
            return
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT id, user_id, username, status, reason, ip_address, user_agent, bundle_id,
                   data_retention_days, anonymize_personal_data, delete_related_data,
                   requested_at, processed_at, scheduled_at, processing_notes, error_message
            FROM account_deactivation
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} deactivation rows")
        deact_map: dict[int, int] = {}
        for row in rows:
            if not User.objects.filter(pk=row["user_id"]).exists():
                self.log_skip(f"deactivation user missing id={row['user_id']}")
                continue
            if self.dry_run:
                deact_map[row["id"]] = row["id"]
                self.stats.migrated += 1
                continue

            def _create(row=row):
                return AccountDeactivation.objects.create(
                    user_id=row["user_id"],
                    state=deactivation_state(row.get("status")),
                    reason=(row.get("reason") or "")[:256],
                    data_retention_days=row.get("data_retention_days") or 30,
                    anonymize_personal_data=bool(row.get("anonymize_personal_data", True)),
                    delete_related_data=bool(row.get("delete_related_data", True)),
                    error_message=row.get("error_message") or "",
                    requested_at=aware_datetime(row.get("requested_at")) or parse_datetime("1970-01-01T00:00:00+00:00"),
                    scheduled_at=aware_datetime(row.get("scheduled_at")),
                    processed_at=aware_datetime(row.get("processed_at")),
                )

            try:
                obj = _create(row=row)
                deact_map[row["id"]] = obj.id
                self.stats.migrated += 1
            except Exception as exc:
                self.log_fail(f"deactivation:{row['id']}", exc)

        if not old_table_exists("deactivation_audit"):
            return
        audits = old_fetch_all(
            """
            SELECT id, deactivation_id, action, description, ip_address, user_agent,
                   success, error_message, metadata, created_at
            FROM deactivation_audit
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(audits)} deactivation audit rows")
        for row in audits:
            new_deact_id = deact_map.get(row["deactivation_id"])
            if not new_deact_id:
                self.log_skip(f"deactivation audit missing parent old_id={row['deactivation_id']}")
                continue
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _audit(row=row, new_deact_id=new_deact_id):
                AccountDeactivationAudit.objects.create(
                    deactivation_id=new_deact_id,
                    action=deactivation_audit_action(row.get("action")),
                    request_id="",
                    details={
                        "legacy_description": row.get("description") or "",
                        "success": bool(row.get("success")),
                        "error_message": row.get("error_message") or "",
                        "metadata": row.get("metadata"),
                        "ip_address": str(row.get("ip_address") or ""),
                        "user_agent": row.get("user_agent") or "",
                    },
                )

            self.run_safe(f"deactivation_audit:{row['id']}", _audit)
            self.stats.migrated += 1
