from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch
from diary_presets.models import Template,Series
from diary_presets.tests import snapshot
from diary_presets.views import publish
from scripts.maintenance.reset_production_business_data import execute

class ProductionResetTests(TestCase):
    def setUp(self):
        self.admin=get_user_model().objects.create_superuser(username='keep',email='keep@example.test',password='safe')
        self.user=get_user_model().objects.create_user(username='remove')
        series=Series.objects.create(slug='test',title='test')
        book=Template.objects.create(series=series,title='test',draft=snapshot())
        publish(book,self.admin)
        import uuid
        private=Template.objects.create(series=series,title='private',audience='private',owner=self.user,customization_id=uuid.uuid4(),draft=snapshot())
        publish(private,self.admin)

    def test_preview_then_apply_preserves_superuser_and_no_oss(self):
        before=get_user_model().objects.filter(pk=self.admin.pk).values().get()
        report=execute(test=True)
        self.assertEqual(get_user_model().objects.count(),2)
        with patch('diary_presets.storage.bucket') as bucket:
            result=execute(True,report['plan_hash'],test=True)
            bucket.assert_not_called()
        self.assertTrue(result['preserved_rows_verified'])
        self.assertEqual(get_user_model().objects.filter(pk=self.admin.pk).values().get(),before)
        self.assertEqual(get_user_model().objects.count(),1)
        self.assertEqual(Template.objects.count(),0)

    def test_changed_plan_refused_without_any_delete(self):
        report=execute(test=True)
        get_user_model().objects.create_user(username='new')
        with self.assertRaisesRegex(RuntimeError,'Plan changed'):execute(True,report['plan_hash'],test=True)
        self.assertEqual(get_user_model().objects.count(),3)
        self.assertEqual(Template.objects.count(),2)
