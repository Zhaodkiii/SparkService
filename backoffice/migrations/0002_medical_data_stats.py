"""TravelDiary: retired medical statistics; preserve migration identity.

Existing legacy tables are intentionally left untouched.
"""
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [("backoffice", "0001_initial") ]
    operations = []
