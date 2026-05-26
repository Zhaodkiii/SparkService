from django.contrib.auth import get_user_model

from accounts.models import NotificationMessage

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all, old_table_exists
from zdk_migration.lib.transforms import json_safe_value, notification_dispatch_status, parse_json_value


class Command(ZdkMigrateCommand):
    help = "Migrate notification_dispatch_log -> accounts_notificationmessage (best effort)"

    def run_migration(self) -> None:
        if not old_table_exists("notification_dispatch_log"):
            self.stdout.write("notification_dispatch_log not found; skipping")
            return
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT id, user_id, event_type, channel, title, body, payload, status,
                   target_count, success_count, failure_count, task_id, error_message,
                   sent_at, created_at, updated_at
            FROM notification_dispatch_log
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} notification dispatch logs")
        target_logs = {}
        if old_table_exists("notification_dispatch_target_log"):
            for trow in old_fetch_all("SELECT * FROM notification_dispatch_target_log ORDER BY id"):
                target_logs.setdefault(trow["dispatch_log_id"], []).append(trow)

        for row in rows:
            if not User.objects.filter(pk=row["user_id"]).exists():
                self.log_skip(f"notification user missing id={row['user_id']}")
                continue
            if self.dry_run:
                self.stats.migrated += 1
                continue

            payload = parse_json_value(row.get("payload"), default={}) or {}
            payload["legacy_event_type"] = row.get("event_type")
            payload["legacy_dispatch_log_id"] = row["id"]
            delivery_details = json_safe_value(target_logs.get(row["id"], []))

            def _create(row=row, payload=payload, delivery_details=delivery_details):
                msg = NotificationMessage.objects.create(
                    user_id=row["user_id"],
                    channel=NotificationMessage.Channel.APNS,
                    status=notification_dispatch_status(row.get("status")),
                    title=row.get("title") or "",
                    body=row.get("body") or "",
                    payload=payload,
                    delivery_details=delivery_details,
                    target_count=row.get("target_count") or 0,
                    success_count=row.get("success_count") or 0,
                    failure_count=row.get("failure_count") or 0,
                    error_message=row.get("error_message") or "",
                )
                NotificationMessage.objects.filter(pk=msg.pk).update(
                    sent_at=row.get("sent_at"),
                    created_at=row.get("created_at") or msg.created_at,
                    updated_at=row.get("updated_at") or msg.updated_at,
                )

            if self.run_safe(f"notification:{row['id']}", _create):
                self.stats.migrated += 1
