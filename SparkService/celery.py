import os

from celery import Celery

# Ensure Django settings are loaded before Celery app config.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SparkService.settings")

app = Celery("SparkService")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

