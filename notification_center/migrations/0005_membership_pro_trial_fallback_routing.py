from django.db import migrations

MEMBERSHIP_FALLBACK_ROUTING = {
    "mode": "fallback",
    "steps": [
        {"channel": "apns", "route_order": 1, "required": False, "success_threshold": "provider_accepted"},
        {"channel": "email", "route_order": 2, "required": False, "success_threshold": "provider_accepted"},
        {"channel": "sms", "route_order": 3, "required": False, "success_threshold": "provider_accepted"},
    ],
}


def apply_membership_fallback_routing(apps, schema_editor):
    Scene = apps.get_model("notification_center", "NotificationBusinessScene")
    Scene.objects.filter(
        key__in=[
            "membership.pro_trial.application_approved",
            "membership.pro_trial.manually_granted",
        ]
    ).update(default_routing=MEMBERSHIP_FALLBACK_ROUTING)
    Scene.objects.filter(key="membership.pro_trial.manually_granted").update(display_name="系统发放试用")


class Migration(migrations.Migration):
    dependencies = [("notification_center", "0004_seed_business_scene_catalog")]

    operations = [migrations.RunPython(apply_membership_fallback_routing, migrations.RunPython.noop)]
