from django.db import migrations


SOURCE_SCOPE = "cn.Zhaodk.Health.web"
TARGET_SCOPE = "cn.Zhaodk.Health"


def merge_health_web_identity_scope(apps, schema_editor):
    SocialIdentity = apps.get_model("accounts", "SocialIdentity")
    AccountDeviceSession = apps.get_model("accounts", "AccountDeviceSession")
    TrustedDevice = apps.get_model("accounts", "TrustedDevice")

    legacy_identities = list(SocialIdentity.objects.filter(bundle_id=SOURCE_SCOPE).order_by("id"))
    for legacy in legacy_identities:
        canonical = (
            SocialIdentity.objects.filter(
                bundle_id=TARGET_SCOPE,
                provider=legacy.provider,
                provider_uid=legacy.provider_uid,
            )
            .order_by("id")
            .first()
        )
        if canonical is None:
            legacy.bundle_id = TARGET_SCOPE
            legacy.save(update_fields=["bundle_id", "updated_at"])
            continue

        if canonical.user_id != legacy.user_id:
            AccountDeviceSession.objects.filter(
                user_id=legacy.user_id,
                bundle_id=SOURCE_SCOPE,
                status="active",
            ).update(status="revoked", revoked_reason="identity_scope_merged")
            TrustedDevice.objects.filter(
                user_id=legacy.user_id,
                bundle_id=SOURCE_SCOPE,
                is_revoked=False,
            ).update(is_revoked=True)
        legacy.delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0014_access_deny_hit")]

    operations = [
        migrations.RunPython(merge_health_web_identity_scope, migrations.RunPython.noop),
    ]
