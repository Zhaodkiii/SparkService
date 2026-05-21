import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("file_manager", "0005_rename_managedfile_file_to_file_path"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="managedfile",
            name="file_manage_user_id_1f7ea3_idx",
        ),
        migrations.RemoveField(
            model_name="managedfile",
            name="business_id",
        ),
        migrations.RemoveField(
            model_name="managedfile",
            name="business_type",
        ),
        migrations.CreateModel(
            name="ManagedFileBusinessRelation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("business_type", models.CharField(db_index=True, max_length=64)),
                ("business_id", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "file",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="business_relations",
                        to="file_manager.managedfile",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="managed_file_business_relations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["user", "business_type", "business_id"],
                        name="file_manage_user_id_1ba16e_idx",
                    ),
                    models.Index(
                        fields=["business_type", "business_id"],
                        name="file_manage_busines_15553a_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("file", "business_type", "business_id"),
                        name="uniq_managed_file_business_relation",
                    ),
                ],
            },
        ),
    ]
