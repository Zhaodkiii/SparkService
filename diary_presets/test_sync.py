"""Production sync regression tests: whole-book atomicity and shared OSS identity."""
import time
import uuid
from copy import deepcopy
from unittest.mock import patch, Mock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import *
from .sync_protocol import *
from .sync_engine import receiver_import, receiver_preflight
from .views import publish
from .tests import snapshot as base_snapshot
from material_library.models import LibraryVersion, LibraryItem, TemplateLibraryBinding, TemplateMaterialLink


@override_settings(MATERIAL_SYNC_ENVIRONMENT_ID='local',DIARY_PRESETS_OSS_PREFIX='traveldiary/presets/')
class PresetSyncTests(TestCase):
    def setUp(self):
        self.admin=get_user_model().objects.create_superuser(username='sync',email='sync@example.test',password='test')
        self.client=APIClient();self.client.force_authenticate(self.admin)
        self.series=Series.objects.create(slug='islands',title='海岛')
        snap=base_snapshot()
        snap['manifest'].update(format='TravelDiary.PresetBook',schemaVersion=1,layerSchemaVersion=1,requiredFonts=[])
        self.book=Template.objects.create(series=self.series,title='海岛手帐',draft=snap)
        publish(self.book,self.admin)
        self.payload=snapshot_for(self.book)
        # A distinct destination identity simulates a second database, without resetting fixtures.
        self.payload['library_id']=str(uuid.uuid4())
        self.payload['book']['snapshot']['manifest']['templateBookID']=self.payload['library_id']
        self.rehash()

    def rehash(self): self.payload['content_hash']=content_hash(self.payload)

    def task(self, payload=None):
        s=payload or self.payload
        actual=inspect_target(s)
        return PresetSyncTask.objects.create(side='target',library_uuid=s['library_id'],source_environment='local',
            source_version=s['source_version'],snapshot=deepcopy(s),content_hash=s['content_hash'],baseline=actual['target_fingerprint'],
            state='queued',idempotency_key=uuid.uuid4().hex,lease_token='lease')

    def apply(self,t):
        with patch('diary_presets.storage.bucket') as bucket:
            bucket.return_value.head_object.return_value=Mock(content_length=1)
            receiver_import(t,'lease')
            bucket.return_value.get_object.assert_not_called()
            bucket.return_value.put_object.assert_not_called()
            bucket.return_value.copy_object.assert_not_called()
        t.refresh_from_db()
        return Template.objects.get(pk=t.library_uuid)

    def add_library(self):
        blob=ResourceBlob.objects.create(sha256='b'*64,object_key=prefix()+'blobs/illustration',byte_size=1,width=512,height=512,mime='image/png')
        material=Material.objects.create(source_identity='test:flower',material_type='sticker')
        rev=MaterialRevision.objects.create(material=material,digest='d'*64,name='花',kind='illustration',subcategory='botanical',resource=blob,thumbnail=blob)
        library=MaterialLibrary.objects.create(template=self.book,title='配套贴纸',library_type='sticker')
        lv=LibraryVersion.objects.create(library=library,number=1,preset_version=self.book.current)
        LibraryItem.objects.create(version=lv,material=material,revision=rev)
        library.current=lv;library.save()
        spec=library_snapshot(lv);spec['id']=str(uuid.uuid4());spec['template_id']=self.payload['library_id']
        self.payload['libraries']=[spec];self.payload['resources']=[dict(sha256=blob.pk,object_key=blob.object_key,byte_size=1,width=512,height=512,mime=blob.mime)]
        self.rehash()
        return spec

    def test_atomic_whole_book_preserves_ids_paths_and_rebuilds_search(self):
        spec=self.add_library();t=self.task();book=self.apply(t)
        self.assertEqual(t.state,'succeeded')
        self.assertEqual(book.current.snapshot,self.payload['book']['snapshot'])
        self.assertEqual(book.current.number,1)
        binding=book.current.material_bindings.get()
        self.assertEqual(str(binding.library_version.library_id),spec['id'])
        self.assertEqual(binding.library_version.items.get().revision.resource.object_key,self.payload['resources'][0]['object_key'])
        self.assertTrue(book.current.search_entries.filter(entity_type='book').exists())
        self.assertEqual(snapshot_for(book)['content_hash'],self.payload['content_hash'])
        receiver_import(t,'lease')
        self.assertEqual(book.versions.count(),1)

    def test_noop_reimport_does_not_create_versions(self):
        self.apply(self.task());t=self.task();self.assertTrue(inspect_target(self.payload)['no_op'])
        self.apply(t)
        self.assertEqual(Version.objects.filter(template_id=self.payload['library_id']).count(),1)

    def test_new_version_preserves_historical_version_and_removes_page_only_from_new(self):
        book=self.apply(self.task());old=book.current
        s=self.payload;s['source_version']=2;snap=s['book']['snapshot'];snap['manifest']['packageVersion']=2
        from .domain import select
        s['book']['snapshot']=select(snap,['b']);self.rehash()
        book=self.apply(self.task())
        self.assertEqual(book.current.number,2);old.refresh_from_db()
        self.assertEqual(len(old.snapshot['pages']),2)
        self.assertEqual(len(book.current.snapshot['pages']),1)

    def test_target_draft_or_manual_edit_prevents_overwrite(self):
        book=self.apply(self.task());book.draft={**book.draft,'changed':True};book.save()
        with self.assertRaisesRegex(SyncError,'未发布'): inspect_target(self.payload)
        book.draft=book.current.snapshot;book.title='人工标题';book.save()
        with self.assertRaisesRegex(SyncError,'被修改'): inspect_target(self.payload)

    def test_preflight_fingerprint_rechecked_before_commit(self):
        t=self.task();self.series.title='人工修改';self.series.save()
        with patch('diary_presets.sync_engine.verify_resources'),self.assertRaises(SyncError): receiver_import(t,'lease')
        self.assertFalse(Template.objects.filter(pk=t.library_uuid).exists())

    def test_missing_oss_no_database_publication(self):
        t=self.task()
        with patch('diary_presets.storage.bucket') as bucket:
            bucket.return_value.head_object.side_effect=RuntimeError('not available')
            with self.assertRaises(SyncError): receiver_import(t,'lease')
        self.assertFalse(Template.objects.filter(pk=t.library_uuid).exists())

    def test_search_index_failure_rolls_back_book_and_dependencies(self):
        spec=self.add_library();t=self.task()
        with patch('diary_presets.sync_engine.verify_resources'),patch('diary_presets.search.index_version',side_effect=RuntimeError('index')):
            with self.assertRaises(RuntimeError): receiver_import(t,'lease')
        self.assertFalse(Template.objects.filter(pk=t.library_uuid).exists())
        self.assertFalse(MaterialLibrary.objects.filter(pk=spec['id']).exists())
        t.refresh_from_db();self.assertEqual(t.commit_status,'not_committed')

    def test_private_paths_missing_files_invalid_hash_rejected(self):
        for mutate in [lambda s:s['book']['snapshot']['keys'].update({'a.json':'private/secret'}),
                       lambda s:s['book']['snapshot']['keys'].pop('a.json'),
                       lambda s:s.update(content_hash='0'*64),
                       lambda s:s['book']['snapshot']['manifest'].update(audience='private')]:
            s=deepcopy(self.payload);mutate(s)
            if s['content_hash']!='0'*64:s['content_hash']=content_hash(s)
            with self.assertRaises(SyncError): validate_snapshot(s)

    def test_source_requires_published_public_book_and_permission(self):
        self.book.active=False;self.book.save()
        with self.assertRaises(SyncError): snapshot_for(self.book)
        user=get_user_model().objects.create_user(username='reader');self.client.force_authenticate(user)
        url=f'/api/admin/v1/diary-presets/templates/{self.book.pk}/production-sync/preflight/'
        self.assertEqual(self.client.post(url,{},format='json').status_code,403)

    @override_settings(MATERIAL_SYNC_SOURCE_ENABLED=True,MATERIAL_SYNC_TARGET_BASE_URL='https://diary.dreamwhale.top',MATERIAL_SYNC_KEY_ID='key',MATERIAL_SYNC_SECRET='secret')
    @patch('diary_presets.sync_api.worker_ready',return_value=True)
    def test_source_preflight_confirm_records_whole_book(self,_):
        url=f'/api/admin/v1/diary-presets/templates/{self.book.pk}/production-sync/preflight/'
        r=self.client.post(url,{'source_version':1,'expected_state_revision':self.book.revision},format='json')
        self.assertEqual(r.status_code,202,r.data)
        t=PresetSyncTask.objects.get(pk=r.data['id']);self.assertEqual(len(t.snapshot['book']['snapshot']['pages']),2)
        t.state='ready';t.baseline='fingerprint';t.expires_at=timezone.now()+__import__('datetime').timedelta(minutes=10);t.save()
        r=self.client.post(f'/api/admin/v1/diary-presets/sync-tasks/{t.pk}/confirm/',{'preflight_token':'fingerprint'},format='json')
        self.assertEqual(r.status_code,202,r.data);t.refresh_from_db();self.assertEqual(t.state,'queued')
        self.assertTrue(Event.objects.filter(action='sync-confirm',template=self.book).exists())

    def test_initial_paid_policy_sales_gate_and_existing_price_preserved(self):
        policy=dict(access_mode='diamond_only',diamond_price=10,currency_code='DIAMOND',pro_entitlement_key=None,bundled_grants=[],terms_version='v1')
        self.payload['initial_policy']=policy
        with override_settings(DIAMOND_REDEMPTION_ENABLED=False),self.assertRaisesRegex(SyncError,'销售'): inspect_target(self.payload)
        with override_settings(DIAMOND_REDEMPTION_ENABLED=True): book=self.apply(self.task())
        offer=ContentOffer.objects.get(target_id=book.pk)
        self.assertEqual(offer.current_policy_revision.diamond_price,10)
        self.payload['initial_policy']={**policy,'diamond_price':99}
        self.apply(self.task());offer.refresh_from_db();self.assertEqual(offer.current_policy_revision.diamond_price,10)

    def test_existing_shared_library_current_not_moved(self):
        spec=self.add_library();spec['template_id']=None;self.rehash()
        library=MaterialLibrary.objects.create(pk=spec['id'],title=spec['title'],library_type='sticker')
        current=LibraryVersion.objects.create(library=library,number=5,content={})
        library.current=current;library.save()
        self.apply(self.task());library.refresh_from_db();self.assertEqual(library.current_id,current.pk)

    @override_settings(MATERIAL_SYNC_ENVIRONMENT_ID='production',MATERIAL_SYNC_RECEIVER_ENABLED=True,MATERIAL_SYNC_ACCEPTED_KEYS={'k':{'secret':'secret','environment':'local'}})
    def test_hmac_prefix_and_replay_protection(self):
        from .sync_transport import signature
        path='/api/v1/preset-sync/capabilities/';stamp=str(int(time.time()));nonce='1'*32
        headers=dict(HTTP_X_SYNC_KEY='k',HTTP_X_SYNC_TIME=stamp,HTTP_X_SYNC_NONCE=nonce,
                     HTTP_X_SYNC_SIGNATURE=signature('secret','GET',path,stamp,nonce,b''))
        client=APIClient();self.assertEqual(client.get(path,**headers).status_code,200)
        self.assertEqual(client.get(path,**headers).status_code,403)

    def test_unknown_result_queries_receipt_before_permission_or_import(self):
        from .tasks import source_step
        t=self.task();t.side='source';t.state='outcome_unknown';t.save()
        result=dict(id='remote',found=True,state='succeeded',commit_status='committed',result={})
        with patch('diary_presets.tasks.remote',return_value=result) as remote:
            self.assertFalse(source_step(t,'lease'))
            self.assertEqual([c.args[0] for c in remote.call_args_list],['GET','GET'])

    def test_adopt_existing_same_version_and_backfill_missing_background(self):
        spec=self.add_library()
        # Existing book imported by the old catalog tool: identical snapshot, no bindings or mapping.
        existing=Template.objects.create(pk=self.payload['library_id'],series=self.series,**{k:v for k,v in self.payload['book'].items() if k!='snapshot'},draft=self.payload['book']['snapshot'])
        existing.current=Version.objects.create(template=existing,number=1,snapshot=existing.draft);existing.save()
        actual=inspect_target(self.payload)
        self.assertTrue(actual['adopt_existing']);self.assertEqual(actual['missing_bindings'],['sticker'])
        book=self.apply(self.task())
        self.assertEqual(book.current_id,existing.current_id);self.assertEqual(book.versions.count(),1)
        self.assertEqual(book.current.material_bindings.count(),1)
        self.assertTrue(PresetSyncMapping.objects.filter(library_uuid=book.pk,target_version=book.current).exists())

    def test_same_version_different_page_bytes_not_adopted(self):
        existing=Template.objects.create(pk=self.payload['library_id'],series=self.series,title=self.book.title,draft=self.payload['book']['snapshot'])
        existing.current=Version.objects.create(template=existing,number=1,snapshot={**existing.draft,'keys':{**existing.draft['keys'],'a.json':prefix()+'blobs/changed'}})
        existing.draft=existing.current.snapshot;existing.save()
        with self.assertRaises(SyncError): inspect_target(self.payload)

    def test_local_legacy_binding_backfill_preserves_version_and_is_idempotent(self):
        from .management.commands.backfill_preset_sync_links import backfill
        self.add_library();number=self.book.current.number
        self.assertEqual(len(backfill()),1)
        self.assertFalse(self.book.current.material_bindings.exists())
        self.assertEqual(len(backfill(True)),1);self.assertEqual(backfill(True),[])
        self.book.refresh_from_db();self.assertEqual(self.book.current.number,number)
