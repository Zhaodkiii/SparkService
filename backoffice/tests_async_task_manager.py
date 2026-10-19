from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
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


class PresetProcessorControlTests(SimpleTestCase):
    @override_settings(DIARY_PRESETS_LOCAL_PROCESSOR_ENABLED=False)
    @patch('scripts.runtime.start')
    def test_external_worker_is_not_started_locally(self, start):
        from backoffice.views import _control_preset_processor
        result = _control_preset_processor('start')
        self.assertEqual(result['action'], 'externally_managed')
        start.assert_not_called()

    @override_settings(DIARY_PRESETS_LOCAL_PROCESSOR_ENABLED=True)
    @patch('scripts.runtime.pid_for', return_value=123)
    @patch('scripts.runtime.owned', return_value=False)
    @patch('scripts.runtime.start', side_effect=RuntimeError('手帐资源处理缺少配置：DIARY_PRESETS_PROCESSOR_TOKEN'))
    def test_configuration_failure_is_visible_to_admin(self, start, owned, pid_for):
        from backoffice.views import _control_preset_processor
        result = _control_preset_processor('start')
        self.assertEqual(result['action'], 'failed')
        self.assertIn('DIARY_PRESETS_PROCESSOR_TOKEN', result['error'])

    @override_settings(DIARY_PRESETS_LOCAL_PROCESSOR_ENABLED=True)
    @patch('scripts.runtime.pid_for', return_value=123)
    @patch('scripts.runtime.owned', return_value=True)
    @patch('scripts.runtime.start')
    def test_repeated_start_uses_existing_process(self, start, owned, pid_for):
        from backoffice.views import _control_preset_processor
        result = _control_preset_processor('start')
        self.assertEqual(result['action'], 'already_running')
        self.assertEqual(result['pid'], 123)

    def test_configuration_check_reports_names_without_secrets(self):
        from diary_presets.processor_runtime import configuration_error
        config = SimpleNamespace(DIARY_PRESETS_PROCESSOR_TOKEN='private-token')
        error = configuration_error(config)
        self.assertIn('ALIYUN_OSS_BUCKET', error)
        self.assertNotIn('private-token', error)
