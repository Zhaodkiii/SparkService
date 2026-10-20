from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('diary_customizations', '0004_direct_photo_upload')]
    operations = [
        migrations.AddField(model_name='operation', name='details', field=models.JSONField(default=dict)),
        migrations.AddField(model_name='operation', name='created_at', field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now), preserve_default=False),
    ]
