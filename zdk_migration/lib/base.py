"""Base class for ZhaodkDream migration management commands."""

from __future__ import annotations

import time
import traceback
from collections import Counter
from dataclasses import dataclass, field

from django.core.management.base import BaseCommand, CommandError

from zdk_migration.lib.error_log import (
    flush_migration_issues,
    normalize_reason,
    record_migration_issue,
    reset_migration_issues,
)
from zdk_migration.lib.id_map import IdMap
from zdk_migration.lib.old_db import old_ping


@dataclass
class MigrationStats:
    migrated: int = 0
    skipped: int = 0
    failed: int = 0
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: "MigrationStats") -> None:
        self.migrated += other.migrated
        self.skipped += other.skipped
        self.failed += other.failed
        self.warnings.extend(other.warnings)


class ZdkMigrateCommand(BaseCommand):
    dry_run: bool = False
    batch_size: int = 500
    command_name: str = ""

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Print actions without writing to new DB")
        parser.add_argument("--batch-size", type=int, default=500, help="Commit every N migrated rows")

    def handle(self, *args, **options):
        self.command_name = self.__class__.__module__.split(".")[-1]
        self.dry_run = bool(options.get("dry_run"))
        self.batch_size = max(1, int(options.get("batch_size") or 500))
        self.id_map = IdMap()
        self.stats = MigrationStats()
        reset_migration_issues(self.command_name)
        started = time.time()
        try:
            ping = old_ping()
            if not ping.get("ok"):
                raise CommandError("Cannot connect to legacy database")
            self.run_migration()
        finally:
            if not self.dry_run:
                self.id_map.save()
            self._flush_issue_log()
        elapsed = time.time() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: migrated={self.stats.migrated} skipped={self.stats.skipped} "
                f"failed={self.stats.failed} elapsed={elapsed:.1f}s dry_run={self.dry_run}"
            )
        )
        self._print_warning_summary()
        if self.stats.failed:
            raise CommandError(f"{self.command_name} finished with {self.stats.failed} failure(s); see errors.log")

    def _flush_issue_log(self) -> None:
        if self.stats.failed or self.stats.skipped:
            record_migration_issue(
                self.command_name,
                "SUMMARY",
                f"migrated={self.stats.migrated} skipped={self.stats.skipped} failed={self.stats.failed}",
                sample_limit=0,
            )
        flush_migration_issues(self.command_name)

    def _print_warning_summary(self) -> None:
        if not self.stats.warnings:
            return
        fails = [w for w in self.stats.warnings if w.startswith("fail:")]
        skips = [w for w in self.stats.warnings if w.startswith("skip:")]
        if fails:
            self.stdout.write(self.style.ERROR(f"Failures ({len(fails)}):"))
            for reason, count in Counter(normalize_reason(w) for w in fails).most_common(10):
                self.stdout.write(self.style.ERROR(f"  [{count}] {reason}"))
            if len(fails) > 10:
                self.stdout.write(self.style.ERROR(f"  ... {len(fails)} total (see errors.log)"))
        if skips:
            self.stdout.write(self.style.WARNING(f"Skips ({len(skips)}):"))
            for reason, count in Counter(normalize_reason(w) for w in skips).most_common(8):
                self.stdout.write(self.style.WARNING(f"  [{count}] {reason}"))
            if len(skips) > 8:
                self.stdout.write(self.style.WARNING(f"  ... {len(skips)} total (see errors.log)"))

    def run_migration(self) -> None:
        raise NotImplementedError

    def log_skip(self, reason: str) -> None:
        self.stats.skipped += 1
        msg = f"skip: {reason}"
        self.stats.warnings.append(msg)
        record_migration_issue(self.command_name, "SKIP", msg)

    def log_fail(self, reason: str, exc: Exception | None = None) -> None:
        self.stats.failed += 1
        detail = f"fail: {reason}"
        if exc is not None:
            detail += f" ({exc})"
        self.stats.warnings.append(detail)
        record_migration_issue(self.command_name, "FAIL", detail)

    def run_safe(self, label: str, fn) -> bool:
        try:
            fn()
            return True
        except Exception as exc:
            self.log_fail(label, exc)
            if self.stats.failed <= 3:
                self.stderr.write(traceback.format_exc())
            return False

    def resolve_mapped_row(self, entity_type: str, old_id, model) -> tuple[bool, int | str | None]:
        """If id_map points at an existing row, return (skip=True, mapped_id).

        If the map is stale (row missing), clear it and return (skip=False, None).
        If unmapped, return (skip=False, None).
        """
        mapped_id = self.id_map.get(entity_type, old_id)
        if mapped_id is None:
            return False, None
        qs = getattr(model, "all_objects", model.objects)
        if qs.filter(pk=mapped_id).exists():
            return True, mapped_id
        self.id_map.pop(entity_type, old_id)
        record_migration_issue(
            self.command_name,
            "WARN",
            f"stale {entity_type} map cleared old_id={old_id} missing target_id={mapped_id}",
        )
        return False, None

    def maybe_commit(self, counter: int) -> None:
        if not self.dry_run and counter > 0 and counter % self.batch_size == 0:
            # ORM auto-commit per save; hook reserved for bulk operations
            pass
