from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("ai_config", "0007_remove_health_scenarios_and_server_tools")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="AIScenarioModelBinding"),
                migrations.DeleteModel(name="TrialModelPolicyItem"),
                migrations.DeleteModel(name="TrialModelPolicy"),
                migrations.DeleteModel(name="AIModelCatalog"),
                migrations.DeleteModel(name="AIProviderKeyConfig"),
                migrations.DeleteModel(name="SmallTask"),
                migrations.DeleteModel(name="TrialApplicationRequest"),
                migrations.DeleteModel(name="TrialApplication"),
                migrations.DeleteModel(name="AIBootstrapProfile"),
            ],
        ),
    ]
