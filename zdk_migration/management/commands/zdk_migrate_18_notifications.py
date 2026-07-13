from zdk_migration.lib.base import ZdkMigrateCommand


class Command(ZdkMigrateCommand):
    help = "Legacy notification migration tombstone; the new notification center starts with empty history"

    def run_migration(self) -> None:
        self.stdout.write("Legacy notification history is intentionally not migrated")
