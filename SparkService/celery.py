import os

from celery import Celery

# Ensure Django settings are loaded before Celery app config.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SparkService.settings")

app = Celery("SparkService")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# ``chat_sync.ai_tasks`` is split by responsibility instead of using the
# conventional single ``tasks.py`` module. Celery autodiscovery therefore does
# not import these modules on its own. Keep every task that the AI worker/beat
# routes reference in the composition root; otherwise the worker can be alive,
# subscribed to the right queues and answer ping while still discarding Outbox
# and recovery jobs as unregistered tasks.
CHAT_AI_TASK_MODULES = (
    "chat_sync.ai_tasks.run_tasks",
    "chat_sync.ai_tasks.outbox_tasks",
    "chat_sync.ai_tasks.recovery_tasks",
    "chat_sync.ai_tasks.knowledge_tasks",
)
app.conf.imports = tuple(dict.fromkeys((*tuple(app.conf.imports or ()), *CHAT_AI_TASK_MODULES)))
