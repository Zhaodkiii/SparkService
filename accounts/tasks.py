"""
Celery task discovery entrypoint for the `accounts` app.

Celery autodiscover looks for `<installed_app>.tasks`, so we re-export
nested tasks modules here.
"""

from accounts.deactivation.tasks import process_deactivation_task  # noqa: F401

