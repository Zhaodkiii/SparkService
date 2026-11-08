from django.db import migrations
from django.db.models import Q


def remove_legacy_configuration(apps, schema_editor):
    connection = schema_editor.connection
    alias = connection.alias
    # Drop dependent tables before their referenced catalog and policy tables.
    tables = (
        "ai_config_aiscenariomodelbinding",
        "ai_config_trialmodelpolicyitem",
        "ai_config_trialmodelpolicy",
        "ai_config_aimodelcatalog",
        "ai_config_aiproviderkeyconfig",
        "ai_config_smalltask",
        "ai_config_trialapplicationrequest",
        "ai_config_trialapplication",
        "ai_config_aibootstrapprofile",
    )
    for table in tables:
        schema_editor.execute(f"DROP TABLE IF EXISTS {schema_editor.quote_name(table)}")

    legacy_codes = (
        "menu:ai:scenario", "menu:ai:models", "menu:ai:small_tasks",
        "menu:ai:provider", "menu:ai:trial", "button:user:pro:grant",
        "button:user:pro:recycle",
    )
    apps.get_model("backoffice", "AdminPermission").objects.using(alias).filter(
        Q(code__in=legacy_codes) | Q(parent_code__in=legacy_codes)
    ).delete()
    apps.get_model("django_celery_beat", "PeriodicTask").objects.using(alias).filter(
        task__startswith="ai_config."
    ).delete()
    apps.get_model("contenttypes", "ContentType").objects.using(alias).filter(
        app_label="ai_config"
    ).delete()
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM django_migrations WHERE app = %s", ["ai_config"])


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ("backoffice", "0007_retire_legacy_ai_permissions"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("django_celery_beat", "0001_initial"),
    ]
    operations = [migrations.RunPython(remove_legacy_configuration)]
