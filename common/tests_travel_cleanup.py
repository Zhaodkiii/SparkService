from types import SimpleNamespace

from django.test import SimpleTestCase
from django.urls import Resolver404, resolve

from file_manager.business_access import user_can_access_file
from notification_center.business_scenes import SCENE_CATALOG


class TravelDiaryBoundaryTests(SimpleTestCase):
    def test_files_are_owner_only_and_deleted_files_are_hidden(self):
        user = SimpleNamespace(id=1, is_authenticated=True)
        own = SimpleNamespace(user_id=1, is_deleted=False)
        other = SimpleNamespace(user_id=2, is_deleted=False)
        deleted = SimpleNamespace(user_id=1, is_deleted=True)
        self.assertTrue(user_can_access_file(user, own))
        self.assertFalse(user_can_access_file(user, other))
        self.assertFalse(user_can_access_file(user, deleted))

    def test_removed_routes_do_not_resolve(self):
        for path in ['/api/v1/ai/chat/capabilities/', '/api/v1/subscriptions/me/', '/api/v1/version/', '/api/v1/content/', '/api/admin/v1/content/', '/api/v1/medical/members/', '/api/v1/nutrition/', '/api/v1/tasks/', '/api/admin/v1/medical-data/users/', '/api/admin/v1/conversations/quick-questions/configs/']:
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)
        resolve('/api/admin/v1/users/')
        resolve('/api/v1/ai/config/bootstrap/')
        resolve('/api/v1/files/register/')
        resolve('/api/v1/oss/sts/credentials/')

    def test_health_notification_scenes_are_not_registered(self):
        self.assertFalse(any(s.key.startswith(('medical.', 'task.')) for s in SCENE_CATALOG))


from importlib import import_module
from django.apps import apps
from django.db import connection
from django.test import TestCase
from backoffice.models import AdminPermission
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from notification_center.models import NotificationBusinessScene


class RetiredConfigurationTests(TestCase):
    def test_upgrade_disables_retired_tasks_and_menus_but_keeps_account_tasks(self):
        interval = IntervalSchedule.objects.create(every=1, period='minutes')
        retired = PeriodicTask.objects.create(name='legacy-chat', task='chat_sync.ai_tasks.run_tasks.run_chat', interval=interval)
        retained = PeriodicTask.objects.create(name='account-security', task='notification_center.tasks.execute_sms_otp_intent_task', interval=interval)
        permission = AdminPermission.objects.create(code='menu:conversations', name='Legacy', permission_type='menu')
        migration = import_module('backoffice.migrations.0004_retire_health_permissions_and_tasks')
        migration.retire_health_entries(apps, SimpleNamespace(connection=connection))
        retired.refresh_from_db()
        retained.refresh_from_db()
        permission.refresh_from_db()
        self.assertFalse(retired.enabled)
        self.assertTrue(retained.enabled)
        self.assertFalse(permission.is_active)

    def test_upgrade_retires_health_notification_scene(self):
        scene = NotificationBusinessScene.objects.create(key='medical.resource.updated', domain='medical', business_type='medical.resource', event_name='updated', display_name='Legacy')
        migration = import_module('notification_center.migrations.0006_retire_health_scenes')
        migration.retire_health_scenes(apps, SimpleNamespace(connection=connection))
        scene.refresh_from_db()
        self.assertEqual(scene.status, 'retired')
