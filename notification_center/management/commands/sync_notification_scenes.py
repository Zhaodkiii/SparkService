from django.core.management.base import BaseCommand

from notification_center.business_scenes import SCENE_CATALOG, sync_business_scenes


class Command(BaseCommand):
    help = "Synchronize the version-controlled notification business-scene catalog."

    def handle(self, *args, **options):
        created, updated = sync_business_scenes()
        self.stdout.write(
            self.style.SUCCESS(
                f"notification scenes synchronized: total={len(SCENE_CATALOG)} created={created} updated={updated}"
            )
        )
