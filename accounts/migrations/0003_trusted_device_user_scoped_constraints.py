from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_account_device_session"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="trusteddevice",
            name="uniq_bundle_device",
        ),
        migrations.AddConstraint(
            model_name="trusteddevice",
            constraint=models.UniqueConstraint(
                fields=("bundle_id", "device_id"),
                condition=Q(user__isnull=True),
                name="uniq_bundle_device_anonymous",
            ),
        ),
        migrations.AddConstraint(
            model_name="trusteddevice",
            constraint=models.UniqueConstraint(
                fields=("bundle_id", "device_id", "user"),
                condition=Q(user__isnull=False),
                name="uniq_bundle_device_user_bound",
            ),
        ),
    ]
