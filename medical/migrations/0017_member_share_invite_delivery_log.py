from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0017_rename_medical_mem_invite_dedup_idx_medical_mem_member__d3f107_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="MemberShareInviteDeliveryLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "invite",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delivery_logs",
                        to="medical.membershareinvite",
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        choices=[("apns", "apns"), ("email", "email"), ("sms", "sms"), ("none", "none")],
                        max_length=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("sent", "sent"), ("failed", "failed"), ("skipped", "skipped")],
                        max_length=10,
                    ),
                ),
                ("provider_message_id", models.CharField(blank=True, default="", max_length=255)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "db_table": "medical_member_share_invite_delivery_log",
                "ordering": ["-created_at"],
            },
        ),
    ]
