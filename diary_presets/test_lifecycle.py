from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from .models import Template,Series,Version,Upload
from backoffice.models import AdminAuditLog
from billing.models import ContentOffer,ContentPolicyDraft

class TemplateLifecycleTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('lifecycle','test@example.test','test')
        self.client=APIClient();self.client.force_authenticate(self.user)
        self.series=Series.objects.create(title='测试',slug='lifecycle')
        self.t=Template.objects.create(series=self.series,title='空草稿',active=False)
        self.base='/api/admin/v1/diary-presets/templates/'
    def preview(self):return self.client.get(self.base+str(self.t.pk)+'/delete-preview/').data
    def post(self,action,**extra):
        self.t.refresh_from_db()
        return self.client.post(self.base+str(self.t.pk)+'/'+action+'/',dict(revision=self.t.revision,reason='清理误建模板',**extra),format='json')
    def test_empty_draft_purge_keeps_independent_audit(self):
        p=self.preview();self.assertTrue(p['quick_delete']);self.assertTrue(p['can_purge'])
        offer=ContentOffer.objects.create(target_kind='template',target_id=self.t.pk,title=self.t.title)
        ContentPolicyDraft.objects.create(offer=offer,actor=self.user,body={})
        self.assertEqual(self.post('permanent-delete',title=self.t.title,expected_preview_hash=p['preview_hash']).status_code,409)
        p=self.preview()
        self.assertEqual(self.post('permanent-delete',title=self.t.title,expected_preview_hash=p['preview_hash']).status_code,200)
        self.assertFalse(Template.objects.filter(pk=self.t.pk).exists())
        self.assertFalse(ContentOffer.objects.filter(pk=offer.pk).exists())
        self.assertTrue(AdminAuditLog.objects.filter(action='template_permanent_delete',resource_id=str(self.t.pk)).exists())
    def test_trash_hides_admin_catalog_and_billing_restore_stays_inactive(self):
        self.assertEqual(self.post('trash').status_code,200)
        self.assertEqual(self.client.get(self.base).data,[])
        self.assertEqual(self.client.get('/api/v1/billing/manage/content-catalog/').data['total'],0)
        self.assertEqual(self.client.get(self.base+'recycle-bin/').data['total'],1)
        self.assertEqual(self.post('restore-from-trash').status_code,200)
        self.t.refresh_from_db();self.assertFalse(self.t.active);self.assertIsNone(self.t.deleted_at)
    def test_published_template_cannot_purge_and_retains_versions_in_trash(self):
        v=Version.objects.create(template=self.t,number=1,snapshot={})
        self.t.current=v;self.t.active=True;self.t.save()
        self.assertFalse(self.preview()['can_purge'])
        self.assertEqual(self.post('trash').status_code,200)
        self.t.refresh_from_db();self.assertTrue(self.t.active)
        self.assertTrue(Version.objects.filter(pk=v.pk).exists())
        self.assertEqual(self.post('permanent-delete',title=self.t.title,expected_preview_hash=self.preview()['preview_hash']).status_code,409)
    def test_running_upload_prevents_trash(self):
        Upload.objects.create(template=self.t,actor=self.user,revision=0,object_key='test',size=1,status='queued')
        self.assertFalse(self.preview()['can_trash']);self.assertEqual(self.post('trash').status_code,409)
    def test_purge_requires_title_and_current_preview(self):
        self.assertEqual(self.post('permanent-delete',title='wrong',expected_preview_hash=self.preview()['preview_hash']).status_code,400)
        self.assertEqual(self.post('permanent-delete',title=self.t.title,expected_preview_hash='stale').status_code,409)
        self.assertTrue(Template.objects.filter(pk=self.t.pk).exists())
    def test_non_superuser_cannot_delete(self):
        user=User.objects.create_user('editor',is_staff=True)
        from django.contrib.auth.models import Permission
        user.user_permissions.add(Permission.objects.get(codename='change_template'))
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(self.base+str(self.t.pk)+'/delete-preview/').status_code,403)
