from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework.test import APIClient
from diary_presets.models import Series, Template, Version
from .models import *
from .lifecycle import bind_published_template, scan_cleanup, execute_cleanup


@override_settings(MIDDLEWARE=[], LOGGING={})
class LifecycleTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser(username='operator',password='test')
        self.client=APIClient();self.client.force_authenticate(self.user)
        for target in ('material_library.views.sign','material_library.catalog_v2.sign'):
            p=patch(target, return_value='https://example.oss/image');p.start();self.addCleanup(p.stop)
        self.series=Series.objects.create(slug='whole-books',title='整本手帐')
        self.book=Template.objects.create(series=self.series,title='苏州手帐')
        self.old_book=Version.objects.create(template=self.book,number=1,snapshot={})
        self.book.current=self.old_book;self.book.save()
        self.lib=MaterialLibrary.objects.create(title='春日贴纸',library_type='sticker')
        self.v1=LibraryVersion.objects.create(library=self.lib,number=1,content={})
        self.lib.current=self.v1;self.lib.save()
        self.base=f'/api/v1/materials/manage/libraries/{self.lib.pk}/'
        self.links=f'/api/v1/materials/manage/templates/{self.book.pk}/links/'

    def link(self, expected=0, **extra):
        return self.client.post(self.links,dict(type='sticker',library_id=str(self.lib.pk),library_version=1,linked=True,expected_revision=expected,**extra),format='json')

    def preview(self): return self.client.get(self.base+'deletion-preview/').data

    def delete(self, **overrides):
        preview=self.preview()
        data=dict(operation='delete',token=preview['token'],expected_state_revision=preview['state_revision'],confirm_title=self.lib.title)
        data.update(overrides)
        return self.client.post(self.base+'recycle/',data,format='json')

    def test_same_package_links_to_multiple_whole_books(self):
        self.assertEqual(self.link().status_code,200)
        other=Template.objects.create(series=self.series,title='杭州手帐')
        response=self.client.post(self.base+'links/',dict(template_id=str(other.pk),linked=True,library_version=1,expected_revision=0),format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.lib.book_links.count(),2)
        self.assertEqual(TemplateLibraryBinding.objects.count(),0)

    def test_conflict_does_not_overwrite_configuration(self):
        self.assertEqual(self.link().status_code,200)
        self.assertEqual(self.link().status_code,409)
        self.assertEqual(TemplateMaterialLink.objects.get().revision,1)

    def test_snapshot_pinned_and_unlink_only_affects_future_publication(self):
        self.link()
        v2=Version.objects.create(template=self.book,number=2,snapshot={})
        bind_published_template(self.book,v2)
        package_v2=LibraryVersion.objects.create(library=self.lib,number=2,content={})
        self.lib.current=package_v2;self.lib.save()
        self.assertEqual(TemplateLibraryBinding.objects.get(preset_version=v2).library_version_id,self.v1.pk)
        response=self.client.post(self.links,dict(type='sticker',linked=False,expected_revision=1),format='json')
        self.assertEqual(response.status_code,200,response.data)
        v3=Version.objects.create(template=self.book,number=3,snapshot={})
        bind_published_template(self.book,v3)
        self.assertFalse(TemplateLibraryBinding.objects.filter(preset_version=v3).exists())
        self.assertTrue(TemplateLibraryBinding.objects.filter(preset_version=v2,library_version=self.v1).exists())

    def test_client_v1_and_v2_resolve_independent_package_from_book_snapshot(self):
        self.link();bind_published_template(self.book,self.old_book)
        self.lib.current=LibraryVersion.objects.create(library=self.lib,number=2,content={});self.lib.save()
        for schema in ('1','2'):
            response=self.client.get('/api/v1/materials/libraries/',dict(schema=schema,template=str(self.book.pk),template_version=1))
            self.assertEqual(response.status_code,200,response.data)
            rows=response.data['items'] if schema=='2' else response.data
            self.assertEqual(rows[0]['version'],1)
            self.assertEqual(rows[0]['id'],str(self.lib.pk))
        other=Template.objects.create(series=self.series,title='同版本号的其他手帐')
        self.assertEqual(self.client.get('/api/v1/materials/libraries/',dict(schema=2,template=str(other.pk),template_version=1)).data['items'],[])

    def test_deleted_or_unpublished_packages_cannot_be_linked(self):
        self.lib.deleted_at=timezone.now();self.lib.save()
        self.assertEqual(self.link().status_code,404)
        self.lib.deleted_at=None;self.lib.current=None;self.lib.save()
        self.assertEqual(self.link().status_code,400)

    def test_delete_blocks_live_links_and_sync(self):
        self.link();self.assertEqual(self.delete().status_code,409)
        self.client.post(self.links,dict(type='sticker',linked=False,expected_revision=1),format='json')
        MaterialSyncTask.objects.create(library_uuid=self.lib.pk,side='source',source_environment='local',source_version=1,content_hash='a'*64,idempotency_key='busy',state='outcome_unknown')
        self.assertEqual(self.delete().status_code,409)

    def test_delete_keeps_history_and_files_restore_stays_withdrawn(self):
        blob=ResourceBlob.objects.create(sha256='c'*64,object_key='traveldiary/presets/blobs/test',byte_size=50,width=1,height=1,mime='image/png')
        self.v1.content={'cover':blob.pk};self.v1.save()
        TemplateLibraryBinding.objects.create(preset_version=self.old_book,library_type='sticker',library_version=self.v1)
        self.assertEqual(self.preview()['resources'],1)
        self.assertEqual(self.delete().status_code,200)
        self.assertEqual(self.client.get('/api/v1/materials/manage/libraries/').data,[])
        self.assertEqual(len(self.client.get('/api/v1/materials/manage/libraries/',dict(recycle=1)).data),1)
        self.assertEqual(self.client.post(self.base+'availability/',dict(expected_state_revision=1,active=True),format='json').status_code,404)
        self.assertTrue(TemplateLibraryBinding.objects.exists());self.assertTrue(ResourceBlob.objects.exists())
        self.lib.refresh_from_db()
        response=self.client.post(self.base+'recycle/',dict(operation='restore',expected_state_revision=self.lib.state_revision),format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.lib.refresh_from_db();self.assertIsNone(self.lib.deleted_at);self.assertFalse(self.lib.active)

    def test_delete_requires_valid_preview_and_exact_title(self):
        self.assertEqual(self.delete(token='bad').status_code,409)
        self.assertEqual(self.delete(confirm_title='错误包名').status_code,400)
        p=self.preview();self.lib.state_revision+=1;self.lib.save()
        self.assertEqual(self.delete(token=p['token']).status_code,409)

    def upload(self, name='old', **extra):
        u=MaterialUpload.objects.create(actor=self.user,purpose='sticker',name=name,object_key='traveldiary/presets/material-uploads/'+name,byte_size=100,sha256='b'*64,expires_at=timezone.now()-timedelta(days=8),upload_metadata={'original':{},'thumbnail':{}},**extra)
        MaterialUpload.objects.filter(pk=u.pk).update(updated_at=timezone.now()-timedelta(days=8))
        return u

    @patch('material_library.lifecycle.bucket')
    def test_cleanup_only_expired_staging_and_retry_is_idempotent(self,bucket):
        u=self.upload(state='verified')
        self.upload('fresh');MaterialUpload.objects.filter(name='fresh').update(updated_at=timezone.now())
        self.upload('notexpired');MaterialUpload.objects.filter(name='notexpired').update(expires_at=timezone.now()+timedelta(hours=1))
        job=scan_cleanup(self.user);self.assertEqual(len(job.entries),1)
        bucket.assert_not_called()
        job=execute_cleanup(job.pk);self.assertEqual(job.state,'completed')
        keys=[call.args[0] for call in bucket.return_value.delete_object.call_args_list]
        self.assertEqual(keys,[u.object_key,u.object_key+'/thumbnail'])
        execute_cleanup(job.pk);self.assertEqual(bucket.return_value.delete_object.call_count,2)
        u.refresh_from_db();self.assertEqual(u.state,'verified');self.assertIsNotNone(u.staging_cleaned_at)
        self.assertEqual(scan_cleanup(self.user).entries,[])

    @patch('material_library.lifecycle.bucket')
    def test_cleanup_failure_redacts_storage_error_and_continues_pending_batches(self,bucket):
        for n in range(12): self.upload(str(n))
        bucket.return_value.delete_object.side_effect=RuntimeError('secret-signed-url')
        job=execute_cleanup(scan_cleanup(self.user).pk)
        self.assertEqual(job.state,'pending')
        job=execute_cleanup(job.pk);self.assertEqual(job.state,'partial')
        self.assertNotIn('secret-signed-url',str(job.entries))
        bucket.return_value.delete_object.side_effect=None
        while job.state in ('partial','pending'):
            job=execute_cleanup(job.pk)
        self.assertEqual(job.state,'completed')

    @patch('material_library.lifecycle.bucket')
    def test_cleanup_rechecks_session_and_rejects_formal_keys(self,bucket):
        u=self.upload();job=scan_cleanup(self.user)
        MaterialUpload.objects.filter(pk=u.pk).update(object_key='traveldiary/presets/blobs/formal')
        job=execute_cleanup(job.pk);self.assertEqual(job.entries[0]['state'],'blocked');bucket.assert_not_called()

    def test_permission_gate_separates_delete_from_edit(self):
        user=get_user_model().objects.create_user(username='editor',password='test')
        user.user_permissions.add(Permission.objects.get(codename='change_template',content_type__app_label='diary_presets'))
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get('/api/v1/materials/manage/options/').data['can_delete'],False)
        self.assertEqual(self.delete().status_code,403)
        self.assertEqual(self.client.post('/api/v1/materials/manage/cleanup/',{},format='json').status_code,403)

    def test_creation_with_book_uses_relation_instead_of_single_owner_and_can_relink(self):
        legacy=MaterialLibrary.objects.create(title='旧贴纸',library_type='sticker',template=self.book)
        TemplateMaterialLink.objects.create(template=self.book,library_type='sticker',library=None,revision=3)
        response=self.client.post('/api/v1/materials/manage/libraries/',dict(title='新贴纸',type='sticker',template_id=str(self.book.pk)),format='json')
        self.assertEqual(response.status_code,201,response.data)
        created=MaterialLibrary.objects.get(pk=response.data['id'])
        self.assertIsNone(created.template_id)
        link=TemplateMaterialLink.objects.get(template=self.book)
        self.assertEqual(link.library_id,created.pk);self.assertEqual(link.revision,4)
        self.assertEqual(legacy.template_id,self.book.pk)

    def test_cleanup_command_dry_run_does_not_write_job_or_delete(self):
        from django.core.management import call_command
        import io
        self.upload()
        output=io.StringIO()
        with patch('material_library.lifecycle.bucket') as bucket:
            call_command('cleanup_material_uploads',stdout=output)
            bucket.assert_not_called()
        self.assertIn('dry-run',output.getvalue())
        self.assertFalse(MaterialCleanupJob.objects.exists())

    def test_reusing_legacy_package_does_not_depend_on_original_book_availability(self):
        self.lib.template=self.book;self.lib.save()
        self.book.active=False;self.book.save()
        from .views import visible
        self.assertTrue(visible().filter(pk=self.lib.pk).exists())
