from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from diary_presets.models import Series,Template
from diary_presets.tests import snapshot
from diary_presets.views import publish
from material_library.models import *
from backoffice.models import ContentSyncBatch
from backoffice.content_sync import make_plan,run_batch,digest

@override_settings(MATERIAL_SYNC_ENVIRONMENT_ID='local-authoring',MATERIAL_SYNC_SOURCE_ENABLED=True,MATERIAL_SYNC_TARGET_BASE_URL='https://diary.dreamwhale.top',MATERIAL_SYNC_KEY_ID='key',MATERIAL_SYNC_SECRET='secret')
class BatchTests(TestCase):
    def setUp(self):
        self.admin=get_user_model().objects.create_superuser(username='admin',email='a@example.test',password='test')
        s=snapshot();s['manifest'].update(format='TravelDiary.PresetBook',schemaVersion=1,layerSchemaVersion=1)
        self.book=Template.objects.create(series=Series.objects.create(slug='test',title='test'),title='test',draft=s)
        publish(self.book,self.admin)
        self.lib=MaterialLibrary.objects.create(template=self.book,title='配套',library_type='sticker')
        self.lv=LibraryVersion.objects.create(library=self.lib,number=1,preset_version=self.book.current)
        self.lib.current=self.lv;self.lib.save()
        TemplateLibraryBinding.objects.create(preset_version=self.book.current,library_type='sticker',library_version=self.lv)
        TemplateMaterialLink.objects.create(template=self.book,library_type='sticker',library=self.lib,library_version=self.lv)

    def plan(self):return make_plan([dict(kind='template',id=str(self.book.pk))])
    def batch(self):
        p=self.plan()
        return ContentSyncBatch.objects.create(actor=self.admin,entries=p,plan_hash=digest(p),state='running',expires_at=timezone.now()+timedelta(minutes=30))

    def test_associated_selection_adds_owner_and_deduplicates(self):
        p=make_plan([dict(kind='material',id=str(self.lib.pk)),dict(kind='template',id=str(self.book.pk))])
        self.assertEqual(len(p),2)
        self.assertEqual(next(e for e in p if e['kind']=='material')['state'],'embedded')

    @patch('diary_presets.tasks.enqueue')
    @patch('backoffice.content_sync.run_batch.apply_async')
    def test_durable_child_and_automatic_preflight_confirmation(self,*_):
        b=self.batch();run_batch(str(b.pk));b.refresh_from_db()
        e=next(e for e in b.entries if e['kind']=='template')
        from diary_presets.models import PresetSyncTask
        task=PresetSyncTask.objects.get(pk=e['task_id'])
        task.state='ready';task.expires_at=timezone.now()+timedelta(minutes=5);task.save()
        run_batch(str(b.pk));task.refresh_from_db();self.assertEqual(task.state,'queued')
        task.state='succeeded';task.save();run_batch(str(b.pk));b.refresh_from_db()
        self.assertEqual(b.state,'succeeded');self.assertTrue(all(e['state']=='succeeded' for e in b.entries))

    @patch('backoffice.content_sync.run_batch.apply_async')
    def test_changed_source_blocks_without_dispatch(self,_):
        b=self.batch();self.book.title='changed';self.book.save()
        run_batch(str(b.pk));b.refresh_from_db()
        self.assertEqual(b.state,'partial')
        from diary_presets.models import PresetSyncTask
        self.assertFalse(PresetSyncTask.objects.exists())

    def test_preview_immutable_and_reader_denied(self):
        c=APIClient();c.force_authenticate(self.admin)
        result=c.post('/api/admin/v1/content-sync/batches/',{'selection':[{'kind':'template','id':str(self.book.pk)}]},format='json')
        self.assertEqual(result.status_code,201,result.data)
        self.assertNotIn('snapshot',result.data['entries'][0])
        c.force_authenticate(get_user_model().objects.create_user(username='reader'))
        self.assertEqual(c.get('/api/admin/v1/content-sync/catalog/').status_code,403)

    def test_unknown_font_fails_closed(self):
        self.book.current.snapshot['manifest']['requiredFonts']=[{'id':'unknown','version':'1'}];self.book.current.save()
        from material_library.sync_protocol import SyncError
        with self.assertRaises(SyncError):self.plan()

    def test_history_sorts_ids_without_large_json_payload(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from rest_framework.test import APIRequestFactory,force_authenticate
        from backoffice.content_sync import Batches
        first=self.batch();second=self.batch()
        request=APIRequestFactory().get('/api/admin/v1/content-sync/batches/')
        force_authenticate(request,user=self.admin)
        with CaptureQueriesContext(connection) as queries:
            response=Batches.as_view()(request)
        self.assertEqual(response.status_code,200)
        self.assertEqual([r['id'] for r in response.data],[str(second.pk),str(first.pk)])
        sort_queries=[q['sql'] for q in queries if 'ORDER BY' in q['sql'] and 'backoffice_contentsyncbatch' in q['sql']]
        self.assertEqual(len(sort_queries),1)
        self.assertNotIn('"entries"',sort_queries[0])
        self.assertNotIn('`entries`',sort_queries[0])
        self.assertTrue(response.data[0]['entries'])

    def test_catalog_completed_version_and_embedded_resources_not_selectable(self):
        from backoffice.content_sync import catalog
        b=self.batch()
        for e in b.entries:e['state']='succeeded'
        b.state='succeeded';b.save()
        rows={r['key']:r for r in catalog()}
        for key in ('template:'+str(self.book.pk),'material:'+str(self.lib.pk)):
            self.assertEqual(rows[key]['sync_state'],'succeeded')
            self.assertFalse(rows[key]['selectable'])
        self.book.title='new title';self.book.save()
        row=next(r for r in catalog() if r['kind']=='template')
        self.assertEqual(row['sync_state'],'pending');self.assertTrue(row['selectable'])

    def test_already_synced_explicit_selection_rejected(self):
        b=self.batch()
        for e in b.entries:e['state']='succeeded'
        b.state='succeeded';b.save()
        c=APIClient();c.force_authenticate(self.admin)
        r=c.post('/api/admin/v1/content-sync/batches/',{'selection':[{'kind':'template','id':str(self.book.pk)}]},format='json')
        self.assertEqual(r.status_code,409)
        self.assertEqual(r.data['code'],'ALREADY_SYNCED')
