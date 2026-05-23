from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_owner_bindings(apps, schema_editor):
    Member = apps.get_model("medical", "Member")
    UserMemberBinding = apps.get_model("medical", "UserMemberBinding")
    for member in Member.objects.filter(is_deleted=False).iterator():
        UserMemberBinding.objects.get_or_create(
            user_id=member.user_id,
            member_id=member.id,
            defaults={
                "relationship": member.relationship or "self",
                "role": "owner",
                "status": "active",
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0010_medicalbasemodel_field_db_comments"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserMemberBinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("relationship", models.CharField(default="self", max_length=64)),
                (
                    "role",
                    models.CharField(
                        choices=[("owner", "owner"), ("admin", "admin"), ("viewer", "viewer")],
                        db_index=True,
                        default="owner",
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "active"), ("revoked", "revoked")],
                        db_index=True,
                        default="active",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invited_member_bindings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_bindings",
                        to="medical.member",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="member_bindings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "medical_user_member_binding",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="usermemberbinding",
            index=models.Index(fields=["member", "status"], name="medical_use_member__b8e0d0_idx"),
        ),
        migrations.AddIndex(
            model_name="usermemberbinding",
            index=models.Index(fields=["user", "status"], name="medical_use_user_id_6f0a8b_idx"),
        ),
        migrations.AddConstraint(
            model_name="usermemberbinding",
            constraint=models.UniqueConstraint(fields=("user", "member"), name="uniq_user_member_binding"),
        ),
        migrations.RunPython(backfill_owner_bindings, migrations.RunPython.noop),
    ]
