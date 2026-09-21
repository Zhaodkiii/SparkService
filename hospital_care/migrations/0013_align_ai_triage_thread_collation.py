from django.db import migrations


def align_ai_triage_thread_collation(apps, schema_editor):
    """Match the existing chat thread UUID collation before cross-app JOINs."""
    if schema_editor.connection.vendor != "mysql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            ALTER TABLE hospital_care_hospitalaitriagebinding
            MODIFY thread_id char(32)
            CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL
            """
        )


class Migration(migrations.Migration):
    dependencies = [
        ("hospital_care", "0012_hospital_ai_triage"),
    ]

    operations = [
        migrations.RunPython(align_ai_triage_thread_collation, migrations.RunPython.noop),
    ]
