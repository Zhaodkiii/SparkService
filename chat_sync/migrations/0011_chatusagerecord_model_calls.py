from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat_sync", "0010_chat_websocket_ticket_session")]

    operations = [
        migrations.AddField("chatusagerecord", "model_calls", models.PositiveIntegerField(default=0)),
    ]