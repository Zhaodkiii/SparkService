from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from SparkService.celery import CHAT_AI_TASK_MODULES, app
from backoffice.views import CHAT_AI_REQUIRED_TASKS, _celery_registered_tasks_status


class CeleryAITaskRegistrationTests(SimpleTestCase):
    def test_celery_composition_root_imports_all_ai_task_modules(self):
        configured = set(app.conf.imports or ())

        self.assertEqual(
            set(CHAT_AI_TASK_MODULES),
            {
                "chat_sync.ai_tasks.run_tasks",
                "chat_sync.ai_tasks.outbox_tasks",
                "chat_sync.ai_tasks.recovery_tasks",
            },
        )
        self.assertTrue(set(CHAT_AI_TASK_MODULES).issubset(configured))

    @patch("backoffice.views.subprocess.run")
    def test_registered_task_status_reports_all_required_tasks(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout="\n".join(CHAT_AI_REQUIRED_TASKS),
            stderr="",
        )

        result = _celery_registered_tasks_status()

        self.assertTrue(result["healthy"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["registered"], list(CHAT_AI_REQUIRED_TASKS))

    @patch("backoffice.views.subprocess.run")
    def test_registered_task_status_exposes_missing_outbox_task(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout="\n".join(
                task for task in CHAT_AI_REQUIRED_TASKS if "outbox_tasks" not in task
            ),
            stderr="",
        )

        result = _celery_registered_tasks_status()

        self.assertFalse(result["healthy"])
        self.assertEqual(
            result["missing"],
            ["chat_sync.ai_tasks.outbox_tasks.relay_chat_event_outbox"],
        )
