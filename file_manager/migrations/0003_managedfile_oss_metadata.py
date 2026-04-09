from django.db import migrations, models


def _managed_file_upload_to(instance, filename):
    return f"managed_files/{instance.user_id}/{instance.file_uuid}/{filename}"


class Migration(migrations.Migration):

    dependencies = [
        ("file_manager", "0002_rename_file_manage_user_id_70bdce_idx_file_manage_user_id_d219e6_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="managedfile",
            name="file",
            field=models.FileField(blank=True, max_length=512, null=True, upload_to=_managed_file_upload_to),
        ),
        migrations.AddField(
            model_name="managedfile",
            name="object_key",
            field=models.CharField(blank=True, default="", max_length=1024),
        ),
        migrations.AddField(
            model_name="managedfile",
            name="storage_type",
            field=models.CharField(blank=True, default="oss", max_length=32),
        ),
    ]
