"""Idempotent index alignment for medical data stats tables.

0002 may be faked or partially applied, and Django auto-generated index names
can differ from the names declared in 0002. This migration ensures the final
index names exist without failing when old names are missing or renames already
happened.
"""

from django.db import migrations


MEMBER_INDEXES = (
    (
        "backoffice_m_total_c_a7d0d0_idx",
        "backoffice__total_c_4b9c95_idx",
        "(`total_count`, `last_medical_updated_at`)",
    ),
    (
        "backoffice_m_refresh_0e8f8f_idx",
        "backoffice__refresh_3b38b2_idx",
        "(`refresh_status`, `refreshed_at`)",
    ),
)

USER_INDEXES = (
    (
        "backoffice_m_last_me_6d8a8a_idx",
        "backoffice__last_me_111335_idx",
        "(`last_medical_updated_at` DESC, `user_id` ASC)",
    ),
    (
        "backoffice_m_medical_8b9b9b_idx",
        "backoffice__medical_be0779_idx",
        "(`medical_data_total` DESC, `user_id` ASC)",
    ),
)


def _table_indexes(cursor, table):
    cursor.execute(f"SHOW INDEX FROM `{table}`")
    return {row[2] for row in cursor.fetchall()}


def _ensure_table_indexes(cursor, table, specs):
    existing = _table_indexes(cursor, table)
    for old_name, new_name, columns_sql in specs:
        if new_name in existing:
            continue
        if old_name in existing:
            cursor.execute(f"ALTER TABLE `{table}` RENAME INDEX `{old_name}` TO `{new_name}`")
            existing.discard(old_name)
            existing.add(new_name)
            continue
        cursor.execute(f"CREATE INDEX `{new_name}` ON `{table}` {columns_sql}")
        existing.add(new_name)


def ensure_indexes(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return

    with connection.cursor() as cursor:
        _ensure_table_indexes(cursor, "backoffice_medical_data_member_stats", MEMBER_INDEXES)
        _ensure_table_indexes(cursor, "backoffice_medical_data_user_stats", USER_INDEXES)


class Migration(migrations.Migration):

    dependencies = [
        ("backoffice", "0002_medical_data_stats"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameIndex(
                    model_name="medicaldatamemberstats",
                    new_name="backoffice__total_c_4b9c95_idx",
                    old_name="backoffice_m_total_c_a7d0d0_idx",
                ),
                migrations.RenameIndex(
                    model_name="medicaldatamemberstats",
                    new_name="backoffice__refresh_3b38b2_idx",
                    old_name="backoffice_m_refresh_0e8f8f_idx",
                ),
                migrations.RenameIndex(
                    model_name="medicaldatauserstats",
                    new_name="backoffice__last_me_111335_idx",
                    old_name="backoffice_m_last_me_6d8a8a_idx",
                ),
                migrations.RenameIndex(
                    model_name="medicaldatauserstats",
                    new_name="backoffice__medical_be0779_idx",
                    old_name="backoffice_m_medical_8b9b9b_idx",
                ),
            ],
            database_operations=[
                migrations.RunPython(ensure_indexes, migrations.RunPython.noop),
            ],
        ),
    ]
