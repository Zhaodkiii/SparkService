from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('print_orders', '0019_printenrollment_review_decision_and_more')]
    operations = [
        migrations.AddField('printcampaign', 'ai_pages_only', models.BooleanField(default=False)),
        migrations.AlterField('printcampaign', 'ai_pages_only', models.BooleanField(default=True)),
        migrations.AddField('printenrollment', 'page_evidence', models.JSONField(default=list)),
    ]
