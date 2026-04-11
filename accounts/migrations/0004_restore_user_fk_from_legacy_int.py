# Replace bigint user_id (0003) with explicit ForeignKey/OneToOne to auth.User.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _link_user_fks(apps, schema_editor):
    User = apps.get_model("auth", "User")

    AccountProfile = apps.get_model("accounts", "AccountProfile")
    for row in AccountProfile.objects.exclude(legacy_profile_user_pk__isnull=True).iterator():
        u = User.objects.filter(pk=row.legacy_profile_user_pk).first()
        if u:
            row.user = u
            row.save(update_fields=["user"])

    LoginAudit = apps.get_model("accounts", "LoginAudit")
    for row in LoginAudit.objects.exclude(legacy_audit_user_pk__isnull=True).iterator():
        u = User.objects.filter(pk=row.legacy_audit_user_pk).first()
        if u:
            row.user = u
            row.save(update_fields=["user"])

    SocialIdentity = apps.get_model("accounts", "SocialIdentity")
    for row in SocialIdentity.objects.exclude(legacy_social_user_pk__isnull=True).iterator():
        u = User.objects.filter(pk=row.legacy_social_user_pk).first()
        if u:
            row.user = u
            row.save(update_fields=["user"])

    AccountDeactivation = apps.get_model("accounts", "AccountDeactivation")
    for row in AccountDeactivation.objects.exclude(legacy_deactivation_user_pk__isnull=True).iterator():
        u = User.objects.filter(pk=row.legacy_deactivation_user_pk).first()
        if u:
            row.user = u
            row.save(update_fields=["user"])

    TrustedDevice = apps.get_model("accounts", "TrustedDevice")
    for row in TrustedDevice.objects.exclude(legacy_trusted_user_pk__isnull=True).iterator():
        u = User.objects.filter(pk=row.legacy_trusted_user_pk).first()
        if u:
            row.user = u
            row.save(update_fields=["user"])

    # Rows whose legacy PK no longer maps to auth_user would violate NOT NULL on profile / identity / deactivation.
    AccountProfile.objects.filter(user__isnull=True).delete()
    SocialIdentity.objects.filter(user__isnull=True).delete()
    AccountDeactivation.objects.filter(user__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_accounts_integer_user_and_trusted_device"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name="accountprofile",
            old_name="user_id",
            new_name="legacy_profile_user_pk",
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="user",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RenameField(
            model_name="loginaudit",
            old_name="user_id",
            new_name="legacy_audit_user_pk",
        ),
        migrations.AddField(
            model_name="loginaudit",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="login_audits",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RenameField(
            model_name="socialidentity",
            old_name="user_id",
            new_name="legacy_social_user_pk",
        ),
        migrations.AddField(
            model_name="socialidentity",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="social_identities",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RenameField(
            model_name="accountdeactivation",
            old_name="user_id",
            new_name="legacy_deactivation_user_pk",
        ),
        migrations.AddField(
            model_name="accountdeactivation",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="deactivations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RenameField(
            model_name="trusteddevice",
            old_name="user_id",
            new_name="legacy_trusted_user_pk",
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="trusted_devices",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(_link_user_fks, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="accountprofile",
            name="legacy_profile_user_pk",
        ),
        migrations.AlterField(
            model_name="accountprofile",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RemoveField(
            model_name="loginaudit",
            name="legacy_audit_user_pk",
        ),
        migrations.RemoveField(
            model_name="socialidentity",
            name="legacy_social_user_pk",
        ),
        migrations.AlterField(
            model_name="socialidentity",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="social_identities",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RemoveField(
            model_name="accountdeactivation",
            name="legacy_deactivation_user_pk",
        ),
        migrations.AlterField(
            model_name="accountdeactivation",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="deactivations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RemoveField(
            model_name="trusteddevice",
            name="legacy_trusted_user_pk",
        ),
    ]
