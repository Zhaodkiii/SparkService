from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import connection

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_count, old_fetch_one, old_ping, old_table_exists


OLD_TABLES = [
    "auth_user",
    "user_profile",
    "auth_identity",
    "trusted_device",
    "login_audit",
    "aera_patient",
    "aera_medical_record",
    "aera_medication",
    "oss_file",
    "messaging_conversation",
]

NEW_TABLES = [
    "auth_user",
    "accounts_accountprofile",
    "medical_member",
    "medical_medicalcase",
    "medical_medication_plan",
    "file_manager_managedfile",
    "chat_sync_chatthread",
]


class Command(ZdkMigrateCommand):
    help = "Preflight checks for ZhaodkDream -> SparkService migration"

    def run_migration(self) -> None:
        ping = old_ping()
        self.stdout.write(f"Legacy DB: {ping['database']}@{ping['host']} ok={ping['ok']}")
        if not ping["ok"]:
            raise CommandError("Legacy database unreachable")

        self.stdout.write("\n=== Legacy table counts ===")
        for table in OLD_TABLES:
            if old_table_exists(table):
                self.stdout.write(f"  {table}: {old_count(table)}")
            else:
                self.stdout.write(self.style.WARNING(f"  {table}: MISSING"))

        orphan = old_fetch_one(
            """
            SELECT COUNT(*) AS c
            FROM aera_medical_record r
            LEFT JOIN aera_patient p ON r.patient_id = p.id
            WHERE p.id IS NULL
            """
        )
        if orphan:
            self.stdout.write(self.style.WARNING(f"Orphan medical records (no patient): {orphan['c']}"))

        self.stdout.write("\n=== New DB business table counts ===")
        with connection.cursor() as cursor:
            for table in NEW_TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                count = cursor.fetchone()[0]
                style = self.style.WARNING if count else self.style.SUCCESS
                self.stdout.write(style(f"  {table}: {count}"))

        User = get_user_model()
        self.stdout.write(f"\nNew auth_user count via ORM: {User.objects.count()}")
        self.stdout.write(self.style.SUCCESS("Preflight complete. Run zdk_migrate_01_auth_users next."))
