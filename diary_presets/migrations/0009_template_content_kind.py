from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('diary_presets', '0008_presetstatisticsstate_presetimportevent_and_more')]
    operations = [migrations.AddField(model_name='template', name='content_kind', field=models.CharField(choices=[('journal', '手帐'), ('album', '相册')], db_index=True, default='journal', max_length=12))]
