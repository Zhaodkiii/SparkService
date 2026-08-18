# MySQL does not support conditional unique constraints (W036).
# The constraint was tracked in migration state but never created in MySQL.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_rename_accounts_ac_dimensi_6a8f2d_idx_accounts_ac_dimensi_58367d_idx"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="accessdenyentry",
                    name="uniq_access_deny_active_dimension_value",
                ),
            ],
        ),
    ]
