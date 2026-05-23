from django.db import migrations, models


def drop_pending_invite_unique_if_exists(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        'ALTER TABLE medical_member_share_invite '
        'DROP CONSTRAINT IF EXISTS uniq_pending_member_share_invite'
    )


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0015_rename_medical_mem_target__a1b2c3_idx_medical_mem_target__29781d_idx_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="membershareinvite",
                    name="uniq_pending_member_share_invite",
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    drop_pending_invite_unique_if_exists,
                    migrations.RunPython.noop,
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="membershareinvite",
            index=models.Index(
                fields=["member", "inviter_user", "target_user", "status"],
                name="medical_mem_invite_dedup_idx",
            ),
        ),
    ]
