from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from backoffice.views import CELERY_MANAGED_TASKS, CELERY_REQUIRED_TASKS, _celery_registered_tasks_status, _celery_worker_queue_names


class CeleryTaskRegistrationTests(SimpleTestCase):
    @patch('backoffice.views.subprocess.run')
    def test_registered_tasks_include_account_security_tasks(self, run):
        run.return_value = SimpleNamespace(returncode=0, stdout='\n'.join(CELERY_REQUIRED_TASKS), stderr='')
        result = _celery_registered_tasks_status()
        self.assertTrue(result['healthy'])
        self.assertEqual(result['missing'], [])

    @patch('backoffice.views.subprocess.run')
    def test_missing_otp_task_makes_worker_unhealthy(self, run):
        missing = 'notification_center.tasks.execute_sms_otp_intent_task'
        run.return_value = SimpleNamespace(returncode=0, stdout='\n'.join(n for n in CELERY_REQUIRED_TASKS if n != missing), stderr='')
        result = _celery_registered_tasks_status()
        self.assertFalse(result['healthy'])
        self.assertEqual(result['missing'], [missing])

    def test_inventory_contains_only_retained_apps(self):
        self.assertTrue(all(n.startswith(('accounts.', 'notification_center.', 'ai_config.')) for n, _, _ in CELERY_MANAGED_TASKS))

    @patch.dict('os.environ', {'CELERY_QUEUES': 'celery,notification.security.high'}, clear=False)
    def test_worker_consumes_security_queue(self):
        queues = _celery_worker_queue_names()
        self.assertIn('notification.security.high', queues)
        self.assertNotIn('default', queues)
