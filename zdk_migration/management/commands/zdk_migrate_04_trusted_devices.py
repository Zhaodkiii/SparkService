from django.contrib.auth import get_user_model

from accounts.models import TrustedDevice

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all
from zdk_migration.lib.transforms import infer_country_code


class Command(ZdkMigrateCommand):
    help = "Migrate trusted_device -> accounts_trusteddevice"

    def run_migration(self) -> None:
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT id, user_id, bundle_id, device_id, push_token, notifications_enabled,
                   app_version, build_version, bundle_identifier, platform, system_version,
                   device_model, device_model_name, device_name, screen_size, screen_scale,
                   time_zone, language_code, region_code, is_simulator, verified,
                   first_seen, last_seen
            FROM trusted_device
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} trusted devices")
        for row in rows:
            bundle_id = row.get("bundle_id") or ""
            device_id = row.get("device_id") or ""
            user_id = row.get("user_id")
            if user_id and not User.objects.filter(pk=user_id).exists():
                user_id = None

            # 新模型：匿名 (bundle_id, device_id, user=NULL) 与用户行 (bundle_id, device_id, user) 各自唯一
            exists_qs = TrustedDevice.objects.filter(bundle_id=bundle_id, device_id=device_id)
            if user_id is None:
                already = exists_qs.filter(user__isnull=True).exists()
            else:
                already = exists_qs.filter(user_id=user_id).exists()
            if already:
                self.stats.skipped += 1
                continue
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, user_id=user_id, bundle_id=bundle_id, device_id=device_id):
                country_code = infer_country_code(
                    language_code=row.get("language_code"),
                    region_code=row.get("region_code"),
                    time_zone=row.get("time_zone"),
                )
                TrustedDevice.objects.create(
                    user_id=user_id,
                    bundle_id=bundle_id,
                    device_id=device_id,
                    push_token=row.get("push_token") or "",
                    notifications_enabled=bool(row.get("notifications_enabled")),
                    app_version=row.get("app_version") or "",
                    build_version=row.get("build_version") or "",
                    bundle_identifier=row.get("bundle_identifier") or "",
                    platform=row.get("platform") or "",
                    system_version=row.get("system_version") or "",
                    device_model=row.get("device_model") or "",
                    device_model_name=row.get("device_model_name") or "",
                    device_name=row.get("device_name") or "",
                    screen_size=row.get("screen_size") or "",
                    screen_scale=row.get("screen_scale"),
                    time_zone=row.get("time_zone") or "",
                    language_code=row.get("language_code") or "",
                    region_code=row.get("region_code") or "",
                    country_code=country_code,
                    is_simulator=bool(row.get("is_simulator")),
                    verified=bool(row.get("verified")),
                    is_revoked=False,
                    first_seen=row.get("first_seen"),
                    last_seen=row.get("last_seen"),
                )

            self.run_safe(f"device:{row['id']}", _create)
            self.stats.migrated += 1
