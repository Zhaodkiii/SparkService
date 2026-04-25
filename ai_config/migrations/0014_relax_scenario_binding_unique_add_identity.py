from django.db import migrations, models


class Migration(migrations.Migration):
    """
    放开场景绑定唯一约束：
    旧约束 uniq_scenario_model_binding         => (scenario, model)
    新约束 uniq_scenario_model_identity_binding => (scenario, model, identity)

    同一个模型现在可以在相同场景下以不同 identity（model / agent）分别绑定。
    """

    dependencies = [
        ('ai_config', '0013_alter_aiscenariomodelbinding_scenario_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='aiscenariomodelbinding',
            name='uniq_scenario_model_binding',
        ),
        migrations.AddConstraint(
            model_name='aiscenariomodelbinding',
            constraint=models.UniqueConstraint(
                fields=['scenario', 'model', 'identity'],
                name='uniq_scenario_model_identity_binding',
            ),
        ),
    ]
