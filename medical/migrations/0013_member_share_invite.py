from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0012_rename_medical_use_member__b8e0d0_idx_medical_use_member__7a5065_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MemberShareInvite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_contact", models.CharField(blank=True, default="", max_length=255)),
                (
                    "channel",
                    models.CharField(
                        choices=[("phone", "phone"), ("email", "email"), ("in_app", "in_app")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("role", models.CharField(default="viewer", max_length=16)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("accepted", "accepted"),
                            ("rejected", "rejected"),
                            ("expired", "expired"),
                            ("cancelled", "cancelled"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "inviter_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sent_member_invites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="share_invites",
                        to="medical.member",
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="received_member_invites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "medical_member_share_invite",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="membershareinvite",
            index=models.Index(fields=["target_user", "status"], name="medical_mem_target__a1b2c3_idx"),
        ),
        migrations.AddIndex(
            model_name="membershareinvite",
            index=models.Index(fields=["member", "status"], name="medical_mem_member__d4e5f6_idx"),
        ),
        migrations.AddConstraint(
            model_name="membershareinvite",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("member", "inviter_user", "target_user"),
                name="uniq_pending_member_share_invite",
            ),
        ),
    ]
