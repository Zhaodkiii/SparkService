from django.contrib.auth import get_user_model

from medical.models import Member, UserMemberBinding

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all
from zdk_migration.lib.transforms import gender_to_member, is_primary_relationship, relationship_to_binding


class Command(ZdkMigrateCommand):
    help = "Migrate aera_patient -> medical_member + medical_user_member_binding"

    def run_migration(self) -> None:
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT id, user_id, name, age, gender, relationship, avatar, birthDate,
                   is_deleted, deleted_at, created_at, updated_at
            FROM aera_patient
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} patients")
        for row in rows:
            old_id = row["id"]
            skip, _ = self.resolve_mapped_row("patient", old_id, Member)
            if skip:
                self.stats.skipped += 1
                continue
            if not User.objects.filter(pk=row["user_id"]).exists():
                self.log_skip(f"patient user missing user_id={row['user_id']}")
                continue
            if self.dry_run:
                self.id_map.set("patient", old_id, old_id)
                self.stats.migrated += 1
                continue

            def _create(row=row, old_id=old_id):
                note_parts = [f"legacy_patient_id={old_id}"]
                if row.get("relationship"):
                    note_parts.append(f"relationship={row['relationship']}")
                if row.get("age"):
                    note_parts.append(f"legacy_age={row['age']}")
                member = Member.all_objects.create(
                    user_id=row["user_id"],
                    name=(row.get("name") or "")[:64],
                    gender=gender_to_member(row.get("gender")),
                    birth_date=row.get("birthDate"),
                    avatar_url=(row.get("avatar") or "")[:512],
                    is_primary=is_primary_relationship(row.get("relationship")),
                    is_deleted=bool(row.get("is_deleted")),
                    deleted_at=row.get("deleted_at"),
                    notes=" | ".join(note_parts),
                )
                Member.all_objects.filter(pk=member.pk).update(
                    created_at=row.get("created_at") or member.created_at,
                    updated_at=row.get("updated_at") or member.updated_at,
                )
                binding, _ = UserMemberBinding.objects.get_or_create(
                    user_id=row["user_id"],
                    member_id=member.id,
                    defaults={
                        "relationship": relationship_to_binding(row.get("relationship")),
                        "role": UserMemberBinding.Role.OWNER,
                        "status": UserMemberBinding.Status.ACTIVE,
                    },
                )
                return member.id

            try:
                new_id = _create()
                self.id_map.set("patient", old_id, new_id)
                self.stats.migrated += 1
            except Exception as exc:
                self.log_fail(f"patient:{old_id}", exc)
