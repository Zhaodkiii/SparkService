from django.db import migrations


def align_chat_join_columns(apps, schema_editor):
    """Match chat_sync UUID collation so JOINs on thread/knowledge_base work.

    Existing chat tables store UUID as utf8mb4_unicode_ci. New hospital_care
    tables inherit the server default utf8mb4_0900_ai_ci. Only the join
    columns are rewritten; whole-table CONVERT would break in-app FKs.
    """
    if schema_editor.connection.vendor != "mysql":
        return
    statements = [
        """
        ALTER TABLE hospital_care_clinicalconversationbinding
        MODIFY thread_id char(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL
        """,
        """
        ALTER TABLE hospital_care_clinicalagentknowledgebinding
        MODIFY knowledge_base_id char(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL
        """,
    ]
    with schema_editor.connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def noop_backfill(apps, schema_editor):
    """Old ChatThread rows are not hospital-owned and must not be backfilled."""


class Migration(migrations.Migration):
    dependencies = [
        ("hospital_care", "0003_conversations"),
    ]

    operations = [
        migrations.RunPython(align_chat_join_columns, migrations.RunPython.noop),
        migrations.RunPython(noop_backfill, migrations.RunPython.noop),
    ]
