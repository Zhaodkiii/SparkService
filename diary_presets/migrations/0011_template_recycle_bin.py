from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('diary_presets', '0010_alter_template_options_presetsynctask_presetsyncslot_and_more')]
    operations = [
        migrations.AddField(model_name='template', name='deleted_at', field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='template', name='deletion_reason', field=models.CharField(blank=True, max_length=500)),
    ]
