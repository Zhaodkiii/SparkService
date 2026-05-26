from django.contrib.auth import get_user_model

from app_version.models import AppVersionConfig, UpdateActionLog, VersionCheckLog

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all, old_table_exists


DEFAULT_BUNDLE_ID = "com.zhaodk.dream"


class Command(ZdkMigrateCommand):
    help = "Migrate app version config and logs"

    def run_migration(self) -> None:
        self._migrate_configs()
        self._migrate_check_logs()

    def _migrate_configs(self) -> None:
        if not old_table_exists("app_version_config"):
            return
        rows = old_fetch_all("SELECT * FROM app_version_config ORDER BY id")
        self.stdout.write(f"Found {len(rows)} version configs")
        for row in rows:
            platform = row.get("platform") or "iOS"
            latest = row.get("latest_version") or "0.0.0"
            if AppVersionConfig.objects.filter(platform=platform, bundle_id=DEFAULT_BUNDLE_ID, latest_version=latest).exists():
                self.stats.skipped += 1
                continue
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, platform=platform, latest=latest):
                return AppVersionConfig.objects.create(
                    platform=platform,
                    bundle_id=DEFAULT_BUNDLE_ID,
                    channel=AppVersionConfig.Channel.PRODUCTION,
                    latest_version=latest,
                    latest_build="",
                    force_update_min_version=row.get("force_update_min_version") or "",
                    force_update_min_build="",
                    update_title=row.get("update_title") or "Update",
                    update_message=row.get("update_message") or "",
                    release_notes=row.get("release_notes") or "",
                    download_url=row.get("download_url") or "https://example.com",
                    enable_gradual_release=bool(row.get("enable_gradual_release")),
                    gradual_release_percentage=row.get("gradual_release_percentage") or 100,
                    gradual_release_min_version=row.get("gradual_release_min_version") or "",
                    is_active=bool(row.get("is_active", True)),
                    created_by_id=row.get("created_by_id"),
                )

            self.run_safe(f"version_config:{row['id']}", _create)
            self.stats.migrated += 1

    def _migrate_check_logs(self) -> None:
        if not old_table_exists("version_check_log"):
            return
        User = get_user_model()
        rows = old_fetch_all("SELECT * FROM version_check_log ORDER BY id")
        self.stdout.write(f"Found {len(rows)} version check logs")
        check_map: dict[int, int] = {}
        for row in rows:
            user_id = row.get("user_id")
            if user_id and not User.objects.filter(pk=user_id).exists():
                user_id = None
            if self.dry_run:
                check_map[row["id"]] = row["id"]
                self.stats.migrated += 1
                continue

            def _create(row=row, user_id=user_id):
                return VersionCheckLog.objects.create(
                    platform=row.get("platform") or "iOS",
                    bundle_id=DEFAULT_BUNDLE_ID,
                    channel="production",
                    current_version=row.get("current_version") or "",
                    current_build="",
                    device_id=row.get("device_id") or "",
                    system_version=row.get("system_version") or "",
                    user_id=user_id,
                    has_update=bool(row.get("has_update")),
                    force_update=bool(row.get("force_update")),
                    latest_version=row.get("latest_version") or "",
                    latest_build="",
                    ip_address=str(row.get("ip_address") or "")[:64],
                )

            try:
                obj = _create()
                check_map[row["id"]] = obj.id
                VersionCheckLog.objects.filter(pk=obj.id).update(checked_at=row.get("checked_at") or obj.checked_at)
                self.stats.migrated += 1
            except Exception as exc:
                self.log_fail(f"version_check_log:{row['id']}", exc)

        if not old_table_exists("update_action_log"):
            return
        actions = old_fetch_all("SELECT * FROM update_action_log ORDER BY id")
        self.stdout.write(f"Found {len(actions)} update action logs")
        for row in actions:
            new_check_id = check_map.get(row.get("check_log_id"))
            if not new_check_id:
                self.log_skip(f"update action missing check_log old_id={row.get('check_log_id')}")
                continue
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _action(row=row, new_check_id=new_check_id):
                obj = UpdateActionLog.objects.create(
                    check_log_id=new_check_id,
                    user_id=row.get("user_id"),
                    action=row.get("action") or UpdateActionLog.Action.DISMISSSED,
                    device_id="",
                    platform="",
                )
                UpdateActionLog.objects.filter(pk=obj.id).update(action_at=row.get("action_at") or obj.action_at)

            self.run_safe(f"update_action:{row['id']}", _action)
            self.stats.migrated += 1
