from django.contrib.auth import get_user_model
from django.db import connection

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_count, old_table_exists


CHECKS = [
    ("users", "auth_user", "auth_user", None),
    ("profiles", "user_profile", "accounts_accountprofile", None),
    ("patients", "aera_patient", "medical_member", None),
    ("medical_records", "aera_medical_record", "medical_medicalcase", None),
    ("medications", "aera_medication", "medical_medication_plan", None),
    ("med_taken", "aera_medication_taken_record", "medical_medication_record", None),
    ("oss_files", "oss_file", "file_manager_managedfile", "status=0"),
    ("conversations", "messaging_conversation", "chat_sync_chatthread", None),
]


class Command(ZdkMigrateCommand):
    help = "Verify migrated row counts and id_map coverage"

    def run_migration(self) -> None:
        self.stdout.write("=== Count comparison (old vs new) ===")
        mismatches = 0
        for label, old_table, new_table, old_where in CHECKS:
            if not old_table_exists(old_table):
                self.stdout.write(self.style.WARNING(f"{label}: old table `{old_table}` missing"))
                continue
            old_w = old_where or "1=1"
            if old_table in {"aera_patient", "aera_medical_record", "aera_medication"}:
                old_w = f"({old_w}) AND is_deleted=0"
            old_c = old_count(old_table, old_w)
            new_w = "is_deleted=0" if new_table.startswith("medical_") or new_table.startswith("file_manager_") else "1=1"
            if new_table == "file_manager_managedfile":
                new_w = "is_deleted=0"
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) FROM `{new_table}` WHERE {new_w}")
                new_c = cursor.fetchone()[0]
            style = self.style.SUCCESS if old_c == new_c else self.style.ERROR
            if old_c != new_c:
                mismatches += 1
            self.stdout.write(style(f"{label}: old={old_c} new={new_c} ({new_table})"))

        self.stdout.write("\n=== id_map.json coverage ===")
        for entity, count in sorted(self.id_map.stats().items()):
            self.stdout.write(f"  {entity}: {count}")

        User = get_user_model()
        self.stdout.write(f"\nauth_user ORM count: {User.objects.count()}")
        if mismatches:
            self.stdout.write(self.style.WARNING(f"Verification finished with {mismatches} count mismatches"))
        else:
            self.stdout.write(self.style.SUCCESS("Verification finished: all compared counts match"))
