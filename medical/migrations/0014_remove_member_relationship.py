from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0013_member_share_invite"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="member",
            name="relationship",
        ),
    ]
