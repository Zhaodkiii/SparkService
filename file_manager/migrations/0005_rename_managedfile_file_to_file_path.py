from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("file_manager", "0004_alter_managedfile_file"),
    ]

    operations = [
        migrations.RenameField(
            model_name="managedfile",
            old_name="file",
            new_name="file_path",
        ),
        migrations.AlterField(
            model_name="managedfile",
            name="file_path",
            field=models.CharField(blank=True, default="", max_length=1024),
        ),
    ]
