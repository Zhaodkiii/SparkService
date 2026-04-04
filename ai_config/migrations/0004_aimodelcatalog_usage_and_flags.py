# Generated manually for AIModelCatalog capability fields

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai_config", "0003_provider_privacy_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="aimodelcatalog",
            name="supports_pricing",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="aimodelcatalog",
            name="supports_text",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="aimodelcatalog",
            name="reasoning_controllable",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="aimodelcatalog",
            name="usage_scenario",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
