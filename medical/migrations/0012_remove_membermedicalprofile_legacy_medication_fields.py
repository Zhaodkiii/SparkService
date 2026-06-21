from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0011_membermedicalprofile_medication_focus"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="membermedicalprofile",
            name="long_term_medications",
        ),
        migrations.RemoveField(
            model_name="membermedicalprofile",
            name="medication_notes",
        ),
    ]
