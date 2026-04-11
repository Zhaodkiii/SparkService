# Generated manually for integer user_id across accounts + TrustedDevice redesign.

import django.utils.timezone
from django.db import migrations, models


def _copy_account_profile_user(apps, schema_editor):
    AccountProfile = apps.get_model("accounts", "AccountProfile")
    for row in AccountProfile.objects.all().iterator():
        AccountProfile.objects.filter(pk=row.pk).update(user_id_new=row.user_id)


def _copy_login_audit_user(apps, schema_editor):
    LoginAudit = apps.get_model("accounts", "LoginAudit")
    for row in LoginAudit.objects.exclude(user_id__isnull=True).iterator():
        LoginAudit.objects.filter(pk=row.pk).update(user_id_new=row.user_id)


def _copy_social_identity_user(apps, schema_editor):
    SocialIdentity = apps.get_model("accounts", "SocialIdentity")
    for row in SocialIdentity.objects.all().iterator():
        SocialIdentity.objects.filter(pk=row.pk).update(user_id_new=row.user_id)


def _copy_account_deactivation_user(apps, schema_editor):
    AccountDeactivation = apps.get_model("accounts", "AccountDeactivation")
    for row in AccountDeactivation.objects.all().iterator():
        AccountDeactivation.objects.filter(pk=row.pk).update(user_id_new=row.user_id)


def _migrate_trusted_device_rows(apps, schema_editor):
    TrustedDevice = apps.get_model("accounts", "TrustedDevice")
    for row in TrustedDevice.objects.all().iterator():
        TrustedDevice.objects.filter(pk=row.pk).update(
            user_id_new=row.user_id,
            device_name=row.nickname or "",
            first_seen=row.created_at,
            last_seen=row.last_seen_at,
        )


def _dedupe_trusted_devices(apps, schema_editor):
    TrustedDevice = apps.get_model("accounts", "TrustedDevice")
    from django.db.models import Count, Min

    dup_keys = (
        TrustedDevice.objects.values("bundle_id", "device_id")
        .annotate(c=Count("id"), min_id=Min("id"))
        .filter(c__gt=1)
    )
    for g in dup_keys:
        bundle_id = g["bundle_id"]
        device_id = g["device_id"]
        keep_id = g["min_id"]
        qs = TrustedDevice.objects.filter(bundle_id=bundle_id, device_id=device_id).order_by("id")
        keeper = qs.first()
        if keeper is None or keeper.id != keep_id:
            keeper = qs.filter(id=keep_id).first() or qs.first()
        if keeper is None:
            continue
        for dup in qs.exclude(pk=keeper.pk):
            if keeper.user_id is None and dup.user_id is not None:
                TrustedDevice.objects.filter(pk=keeper.pk).update(user_id=dup.user_id)
                keeper.user_id = dup.user_id
            dup.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_socialidentity"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="trusteddevice",
            name="uniq_trusted_device_per_user",
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="user_id_new",
            field=models.BigIntegerField(null=True),
        ),
        migrations.RunPython(_copy_account_profile_user, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="accountprofile",
            name="user",
        ),
        migrations.RenameField(
            model_name="accountprofile",
            old_name="user_id_new",
            new_name="user_id",
        ),
        migrations.AlterField(
            model_name="accountprofile",
            name="user_id",
            field=models.BigIntegerField(db_index=True, unique=True),
        ),
        migrations.AddField(
            model_name="loginaudit",
            name="user_id_new",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(_copy_login_audit_user, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="loginaudit",
            name="user",
        ),
        migrations.RenameField(
            model_name="loginaudit",
            old_name="user_id_new",
            new_name="user_id",
        ),
        migrations.AlterField(
            model_name="loginaudit",
            name="user_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="socialidentity",
            name="user_id_new",
            field=models.BigIntegerField(null=True),
        ),
        migrations.RunPython(_copy_social_identity_user, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="socialidentity",
            name="user",
        ),
        migrations.RenameField(
            model_name="socialidentity",
            old_name="user_id_new",
            new_name="user_id",
        ),
        migrations.AlterField(
            model_name="socialidentity",
            name="user_id",
            field=models.BigIntegerField(db_index=True),
        ),
        migrations.AddField(
            model_name="accountdeactivation",
            name="user_id_new",
            field=models.BigIntegerField(null=True),
        ),
        migrations.RunPython(_copy_account_deactivation_user, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="accountdeactivation",
            name="user",
        ),
        migrations.RenameField(
            model_name="accountdeactivation",
            old_name="user_id_new",
            new_name="user_id",
        ),
        migrations.AlterField(
            model_name="accountdeactivation",
            name="user_id",
            field=models.BigIntegerField(db_index=True),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="user_id_new",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="push_token",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="notifications_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="app_version",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="build_version",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="bundle_identifier",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="platform",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="system_version",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="device_model",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="device_model_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="device_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="screen_size",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="screen_scale",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="time_zone",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="language_code",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="region_code",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="is_simulator",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="first_seen",
            field=models.DateTimeField(default=django.utils.timezone.now, null=True),
        ),
        migrations.AddField(
            model_name="trusteddevice",
            name="last_seen",
            field=models.DateTimeField(default=django.utils.timezone.now, null=True),
        ),
        migrations.RunPython(_migrate_trusted_device_rows, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="trusteddevice",
            name="user",
        ),
        migrations.RenameField(
            model_name="trusteddevice",
            old_name="user_id_new",
            new_name="user_id",
        ),
        migrations.RemoveField(
            model_name="trusteddevice",
            name="nickname",
        ),
        migrations.RemoveField(
            model_name="trusteddevice",
            name="created_at",
        ),
        migrations.RemoveField(
            model_name="trusteddevice",
            name="last_seen_at",
        ),
        migrations.AlterField(
            model_name="trusteddevice",
            name="bundle_id",
            field=models.CharField(db_index=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="trusteddevice",
            name="device_id",
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.RunPython(_dedupe_trusted_devices, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="trusteddevice",
            name="first_seen",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="trusteddevice",
            name="last_seen",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="trusteddevice",
            name="user_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="trusteddevice",
            constraint=models.UniqueConstraint(fields=("bundle_id", "device_id"), name="uniq_bundle_device"),
        ),
    ]
