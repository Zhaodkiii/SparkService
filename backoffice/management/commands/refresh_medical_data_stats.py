from django.core.management.base import BaseCommand

from backoffice.medical_data_stats_service import refresh_global_stats, refresh_member_stats, refresh_user_stats
from medical.models import Member, UserMemberBinding


class Command(BaseCommand):
    help = "Refresh backoffice medical data pre-aggregated stats (BACKOFFICE-MED-000001)"

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, help="Refresh stats for a single user")
        parser.add_argument("--member-id", type=int, help="Refresh stats for a single member")

    def handle(self, *args, **options):
        user_id = options.get("user_id")
        member_id = options.get("member_id")

        if member_id:
            refresh_member_stats(member_id)
            self.stdout.write(self.style.SUCCESS(f"member stats refreshed: {member_id}"))
            return

        if user_id:
            refresh_user_stats(user_id)
            self.stdout.write(self.style.SUCCESS(f"user stats refreshed: {user_id}"))
            refresh_global_stats()
            return

        member_ids = Member.objects.filter(is_deleted=False).values_list("id", flat=True)
        for mid in member_ids:
            refresh_member_stats(mid)

        user_ids = (
            UserMemberBinding.objects.filter(status=UserMemberBinding.Status.ACTIVE)
            .values_list("user_id", flat=True)
            .distinct()
        )
        for uid in user_ids:
            refresh_user_stats(uid)

        refresh_global_stats()
        self.stdout.write(self.style.SUCCESS(f"refreshed members={len(member_ids)} users={len(list(user_ids))}"))
