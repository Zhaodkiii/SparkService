# Generated for §18 editor role

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0017_member_share_invite_delivery_log"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usermemberbinding",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "owner"),
                    ("admin", "admin"),
                    ("editor", "editor"),
                    ("viewer", "viewer"),
                ],
                db_index=True,
                default="owner",
                max_length=16,
            ),
        ),
    ]
