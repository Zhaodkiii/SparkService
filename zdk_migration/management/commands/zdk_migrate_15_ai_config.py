from django.contrib.auth import get_user_model

from ai_config.models import AIModelCatalog, AIProviderKeyConfig, TrialApplication, TrialModelPolicy, TrialModelPolicyItem

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.crypto import decrypt_legacy_api_key
from zdk_migration.lib.old_db import old_fetch_all, old_table_exists
from zdk_migration.lib.transforms import normalize_migrated_trial, trial_status_to_new, usage_kind_to_scenario


class Command(ZdkMigrateCommand):
    help = "Migrate trial applications, provider keys, and trial model policies"

    def run_migration(self) -> None:
        self._migrate_providers()
        self._migrate_trial_applications()
        self._repair_expired_legacy_trials()
        self._migrate_trial_policies()

    def _migrate_providers(self) -> None:
        if not old_table_exists("aera_ai_provider_key_config"):
            return
        rows = old_fetch_all("SELECT * FROM aera_ai_provider_key_config ORDER BY priority, id")
        self.stdout.write(f"Found {len(rows)} provider key configs")
        for row in rows:
            code = (row.get("provider_code") or "").strip()
            if not code:
                continue
            company = code.upper()[:64]
            name = code[:128]
            if AIProviderKeyConfig.objects.filter(kind="api", company=company, name=name).exists():
                self.stats.skipped += 1
                continue
            plain_key = decrypt_legacy_api_key(row.get("api_key_encrypted") or "")
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, code=code, company=company, name=name, plain_key=plain_key):
                AIProviderKeyConfig.objects.create(
                    kind=AIProviderKeyConfig.Kind.API,
                    name=name,
                    company=company,
                    key=plain_key,
                    request_url=row.get("endpoint") or "",
                    is_hidden=False,
                    is_using=bool(row.get("enabled", True)),
                    help=row.get("help_url") or "",
                    privacy_policy_url=row.get("privacy_policy_url") or "",
                    source=AIProviderKeyConfig.Source.SYSTEM,
                    position=row.get("priority") or 0,
                    is_active=bool(row.get("enabled", True)),
                )

            self.run_safe(f"provider:{code}", _create)
            self.stats.migrated += 1

    def _trial_note(self, row) -> str:
        note_parts = []
        if row.get("reject_reason"):
            note_parts.append(str(row["reject_reason"]))
        if row.get("revoke_reason"):
            note_parts.append(str(row["revoke_reason"]))
        return " | ".join(note_parts)[:255]

    def _trial_fields(self, row):
        status = trial_status_to_new(row.get("status"))
        status, started_at, expires_at, applied_at, renewed = normalize_migrated_trial(
            old_status=row.get("status"),
            status=status,
            started_at=row.get("created_at") if status == "active" else None,
            expires_at=row.get("expires_at"),
            applied_at=row.get("created_at"),
        )
        note = self._trial_note(row)
        if renewed:
            suffix = "legacy trial renewed on migration"
            note = f"{note} | {suffix}".strip(" |")[:255]
        return {
            "status": status,
            "started_at": started_at,
            "expires_at": expires_at,
            "applied_at": applied_at,
            "approved_at": row.get("updated_at") if status == "active" else None,
            "rejected_at": row.get("updated_at") if status == "rejected" else None,
            "note": note,
            "renewed": renewed,
        }

    def _migrate_trial_applications(self) -> None:
        if not old_table_exists("aera_trial_application"):
            return
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT t.*
            FROM aera_trial_application t
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM aera_trial_application
                GROUP BY user_id
            ) x ON t.user_id = x.user_id AND t.id = x.max_id
            ORDER BY t.id
            """
        )
        self.stdout.write(f"Found {len(rows)} trial applications (latest per user)")
        for row in rows:
            user_id = row["user_id"]
            if not User.objects.filter(pk=user_id).exists():
                self.log_skip(f"trial user missing id={user_id}")
                continue

            fields = self._trial_fields(row)
            existing = TrialApplication.objects.filter(user_id=user_id).first()
            if existing:
                if self._sync_trial_row(existing, fields, dry_run=self.dry_run):
                    self.stats.migrated += 1
                else:
                    self.stats.skipped += 1
                continue

            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, fields=fields):
                TrialApplication.objects.create(
                    user_id=user_id,
                    status=fields["status"],
                    grant_source=TrialApplication.GrantSource.APPLICATION,
                    started_at=fields["started_at"],
                    expires_at=fields["expires_at"],
                    applied_at=fields["applied_at"],
                    approved_at=fields["approved_at"],
                    rejected_at=fields["rejected_at"],
                    note=fields["note"],
                )

            self.run_safe(f"trial_app:{row['id']}", _create)
            self.stats.migrated += 1

    def _sync_trial_row(self, trial: TrialApplication, fields: dict, *, dry_run: bool) -> bool:
        """Update migrated trials that were created with expired expires_at."""
        if fields["status"] != TrialApplication.Status.ACTIVE:
            return False
        if trial.is_active_trial() and not fields["renewed"]:
            return False
        if not fields["renewed"] and trial.status == TrialApplication.Status.ACTIVE:
            return False
        if dry_run:
            return True
        trial.status = TrialApplication.Status.ACTIVE
        trial.started_at = fields["started_at"]
        trial.expires_at = fields["expires_at"]
        trial.applied_at = fields["applied_at"] or trial.applied_at
        trial.approved_at = fields["approved_at"] or trial.approved_at
        if fields["note"]:
            trial.note = fields["note"]
        trial.save(
            update_fields=[
                "status",
                "started_at",
                "expires_at",
                "applied_at",
                "approved_at",
                "note",
                "updated_at",
            ]
        )
        return True

    def _repair_expired_legacy_trials(self) -> None:
        """Re-sync any legacy-approved user whose trial row is still expired in new DB."""
        if not old_table_exists("aera_trial_application"):
            return
        rows = old_fetch_all(
            """
            SELECT t.*
            FROM aera_trial_application t
            INNER JOIN (
                SELECT user_id, MAX(id) AS max_id
                FROM aera_trial_application
                GROUP BY user_id
            ) x ON t.user_id = x.user_id AND t.id = x.max_id
            WHERE t.status IN ('approved', 'active')
            ORDER BY t.id
            """
        )
        repaired = 0
        for row in rows:
            trial = TrialApplication.objects.filter(user_id=row["user_id"]).first()
            if not trial or trial.is_active_trial():
                continue
            fields = self._trial_fields(row)
            if not fields["renewed"]:
                continue
            if self._sync_trial_row(trial, fields, dry_run=self.dry_run):
                repaired += 1
        if repaired:
            self.stdout.write(f"Renewed {repaired} expired legacy trials")
            self.stats.migrated += repaired

    def _ensure_catalog_model(self, model_name: str, display_name: str = "") -> AIModelCatalog:
        catalog, _ = AIModelCatalog.objects.get_or_create(
            name=model_name,
            defaults={
                "display_name": (display_name or model_name)[:128],
                "company": "LEGACY",
                "source": AIModelCatalog.Source.SYSTEM,
            },
        )
        return catalog

    def _migrate_trial_policies(self) -> None:
        if not old_table_exists("aera_trial_model_policy"):
            return
        policies = old_fetch_all("SELECT * FROM aera_trial_model_policy ORDER BY id")
        self.stdout.write(f"Found {len(policies)} trial policies")
        policy_map: dict[int, int] = {}
        for row in policies:
            key = f"legacy_policy_{row['id']}"
            policy, created = TrialModelPolicy.objects.get_or_create(
                key=key,
                defaults={
                    "name": f"Legacy Policy {row['id']}",
                    "description": f"default_model={row.get('default_model_name') or ''}",
                    "is_active": bool(row.get("enabled", True)),
                },
            )
            policy_map[row["id"]] = policy.id
            if created:
                self.stats.migrated += 1
            else:
                self.stats.skipped += 1

        if not old_table_exists("aera_trial_model_policy_item"):
            return
        items = old_fetch_all("SELECT * FROM aera_trial_model_policy_item ORDER BY id")
        self.stdout.write(f"Found {len(items)} trial policy items")
        for row in items:
            new_policy_id = policy_map.get(row.get("policy_id"))
            if not new_policy_id:
                self.log_skip(f"policy item missing policy old_id={row.get('policy_id')}")
                continue
            model_name = (row.get("model_name") or "").strip()
            if not model_name:
                continue
            scenario = usage_kind_to_scenario(row.get("usage_kind"))
            catalog = self._ensure_catalog_model(model_name, row.get("display_name") or model_name)
            if TrialModelPolicyItem.objects.filter(policy_id=new_policy_id, scenario=scenario, model=catalog).exists():
                self.stats.skipped += 1
                continue
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, new_policy_id=new_policy_id, scenario=scenario, catalog=catalog):
                TrialModelPolicyItem.objects.create(
                    policy_id=new_policy_id,
                    scenario=scenario,
                    model=catalog,
                    temperature=0.2,
                    max_tokens=2048,
                    position=row.get("price") or 0,
                    is_default=False,
                    is_active=True,
                    brief_description=row.get("display_name") or "",
                )

            self.run_safe(f"trial_policy_item:{row['id']}", _create)
            self.stats.migrated += 1
