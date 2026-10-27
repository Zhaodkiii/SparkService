import copy
import hashlib
import json
import time
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings, RequestFactory
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate
from .models import *
from .sync_protocol import *
from .sync_engine import receiver_import, receiver_preflight, claim
from .sync_transport import signature, authorize
from .sync_api import SourcePreflight, SourceConfirm, ReceivePreflight, ReceiveImport, ReceiveByKey


@override_settings(MATERIAL_SYNC_ENVIRONMENT_ID='local-authoring',MATERIAL_SYNC_SOURCE_ENABLED=True,
 MATERIAL_SYNC_TARGET_BASE_URL='https://diary.dreamwhale.top',MATERIAL_SYNC_KEY_ID='test',MATERIAL_SYNC_SECRET='test-only-secret')
class SyncTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser(username='sync-admin',password='test')
        self.blobs=[]
        for n in range(3):
            sha=hashlib.sha256(str(n).encode()).hexdigest()
            self.blobs.append(ResourceBlob.objects.create(sha256=sha,object_key=prefix()+'blobs/'+sha,byte_size=10,width=256 if n==1 else 1024,height=256 if n==1 else 1024,mime='image/png'))
        m=Material.objects.create(source_identity='authored:sync-test:01',material_type='sticker')
        from .services import revision
        self.rev=revision(m,dict(name='小猪',kind='illustration',subcategory='object',keywords=['夏日'],aliases=[],sources=[],resource_id=self.blobs[0].pk,thumbnail_id=self.blobs[1].pk))
        self.lib=MaterialLibrary.objects.create(title='测试贴纸',library_type='sticker')
        content=dict(title='测试贴纸',description='',tags=[],cover=self.blobs[2].pk,previews=[self.blobs[2].pk],items=[{'revision':self.rev.pk}])
        v=LibraryVersion.objects.create(library=self.lib,number=1,content=content)
        LibraryItem.objects.create(version=v,material=m,revision=self.rev,position=0)
        self.lib.current=v;self.lib.save();LibraryDraft.objects.create(library=self.lib,content=content,base_version=1)
        self.s=snapshot_for(self.lib)

    def target_snapshot(self):
        s=copy.deepcopy(self.s);s['library_id']=str(uuid.uuid4());s['content_hash']=content_hash(s);return s

    def task(self,s=None):
        s=s or self.s
        result=inspect_target(s)
        return MaterialSyncTask.objects.create(side='target',source_environment='local-authoring',library_uuid=s['library_id'],source_version=1,content_hash=s['content_hash'],snapshot=s,baseline=result['target_fingerprint'],idempotency_key=uuid.uuid4().hex,state='queued',lease_token='test')

    def test_portable_hash_ignores_environment_and_source_version(self):
        s=copy.deepcopy(self.s);s['source_version']=77;s['source_environment']='other'
        self.assertEqual(content_hash(s),self.s['content_hash'])

    def test_protocol_rejects_private_path_and_payload(self):
        for mutate in [lambda s:s.update(extra='image'),lambda s:s['resources'][0].update(object_key='private/a'),lambda s:s['items'].append(s['items'][0])]:
            s=copy.deepcopy(self.s);mutate(s)
            with self.assertRaises(SyncError):validate_snapshot(s)

    @patch('material_library.sync_engine.verify_resources')
    def test_create_and_repeated_import_keep_one_version(self,verify):
        s=self.target_snapshot();t=self.task(s);receiver_import(t,'test');t.refresh_from_db()
        lib=MaterialLibrary.objects.get(pk=s['library_id'])
        self.assertEqual(lib.current.items.count(),1);self.assertEqual(t.state,'succeeded')
        t2=self.task(s);receiver_import(t2,'test');lib.refresh_from_db()
        self.assertEqual(lib.versions.count(),1)
        self.assertEqual(lib.current.items.get().revision_id,self.rev.pk)

    @patch('material_library.sync_engine.verify_resources')
    def test_incremental_update_preserves_operational_settings(self,verify):
        t=self.task();receiver_import(t,'test')
        self.lib.featured=True;self.lib.sort_order=42;self.lib.save()
        s=copy.deepcopy(self.s);s['library']['description']='新增介绍';s['content_hash']=content_hash(s)
        t=self.task(s);receiver_import(t,'test');self.lib.refresh_from_db()
        self.assertEqual(self.lib.current.number,2);self.assertTrue(self.lib.featured);self.assertEqual(self.lib.sort_order,42)
        self.assertEqual(self.lib.versions.count(),2)

    def test_target_draft_and_withdrawal_block(self):
        self.lib.active=False;self.lib.save()
        with self.assertRaisesMessage(SyncError,'已下架'):inspect_target(self.s)
        self.lib.active=True;self.lib.save();d=self.lib.draft;d.content={**d.content,'description':'人工草稿'};d.save()
        with self.assertRaisesMessage(SyncError,'草稿'):inspect_target(self.s)

    @patch('material_library.sync_engine.verify_resources')
    def test_baseline_change_prevents_commit(self,verify):
        t=self.task();self.lib.state_revision+=1;self.lib.save()
        with self.assertRaisesMessage(SyncError,'已改变'):receiver_import(t,'test')
        self.assertEqual(self.lib.versions.count(),1)

    @patch('material_library.sync_engine.verify_resources')
    def test_transaction_rolls_back_partial_import(self,verify):
        s=self.target_snapshot();t=self.task(s)
        with patch('material_library.sync_engine.MaterialAudit.objects.create',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):receiver_import(t,'test')
        self.assertFalse(MaterialLibrary.objects.filter(pk=s['library_id']).exists())
        t.refresh_from_db();self.assertEqual(t.commit_status,'not_committed')

    def test_identity_collision_rejected(self):
        s=copy.deepcopy(self.s);s['materials'][0]['source_identity']='other';s['content_hash']=content_hash(s)
        with self.assertRaisesMessage(SyncError,'身份冲突'):inspect_target(s)

    def test_oss_head_only(self):
        bucket=MagicMock();bucket.head_object.return_value=MagicMock(content_length=10,headers={'Content-Type':'image/png'})
        with patch('diary_presets.storage.bucket',return_value=bucket):verify_resources(self.s)
        self.assertEqual(bucket.head_object.call_count,3);bucket.get_object.assert_not_called();bucket.put_object.assert_not_called()
        bucket.head_object.return_value.content_length=11
        with patch('diary_presets.storage.bucket',return_value=bucket):
            with self.assertRaises(SyncError):verify_resources(self.s)

    @override_settings(MATERIAL_SYNC_RECEIVER_ENABLED=True,MATERIAL_SYNC_ENVIRONMENT_ID='production',MATERIAL_SYNC_ACCEPTED_KEYS={'test':{'secret':'test-only-secret','environment':'local-authoring'}})
    def test_hmac_and_nonce_replay(self):
        body=canonical({'hello':'world'});path='/api/v1/material-sync/preflights/';stamp=str(int(time.time()));nonce='a'*32
        req=RequestFactory().post(path,body,content_type='application/json',HTTP_X_SYNC_KEY='test',HTTP_X_SYNC_TIME=stamp,HTTP_X_SYNC_NONCE=nonce,HTTP_X_SYNC_SIGNATURE=signature('test-only-secret','POST',path,stamp,nonce,body))
        self.assertEqual(authorize(req),'local-authoring')
        with self.assertRaisesMessage(SyncError,'已处理'):authorize(req)

    def test_source_permission_and_worker_requirement(self):
        req=APIRequestFactory().post('/api/v1/materials/manage/',{'source_version':1,'expected_state_revision':0},format='json')
        force_authenticate(req,user=self.user)
        with patch('material_library.sync_api.worker_ready',return_value=False):
            r=SourcePreflight.as_view()(req,pk=self.lib.pk)
        self.assertEqual(r.status_code,409);self.assertEqual(r.data['code'],'WORKER_UNAVAILABLE')
        user=get_user_model().objects.create_user(username='ordinary')
        req=APIRequestFactory().post('/api/v1/materials/manage/',{},format='json');force_authenticate(req,user=user)
        self.assertEqual(SourcePreflight.as_view()(req,pk=self.lib.pk).status_code,403)

    @patch('material_library.tasks.enqueue')
    @patch('material_library.sync_api.worker_ready',return_value=True)
    def test_confirmation_rejects_source_change(self,*_):
        t=MaterialSyncTask.objects.create(side='source',source_environment='local-authoring',library_uuid=self.lib.pk,source_version=1,content_hash=self.s['content_hash'],snapshot=self.s,state='ready',baseline='x',expires_at=timezone.now()+timedelta(minutes=5),idempotency_key=uuid.uuid4().hex)
        self.lib.active=False;self.lib.save()
        req=APIRequestFactory().post('/api/v1/materials/manage/',{'preflight_token':'x'},format='json');force_authenticate(req,user=self.user)
        self.assertEqual(SourceConfirm.as_view()(req,pk=t.pk).status_code,409)

    def test_lease_excludes_duplicate_worker(self):
        t=self.task();self.assertTrue(claim(t.pk));self.assertIsNone(claim(t.pk))

    def test_receiver_body_size_guard(self):
        from .middleware import MaterialControlPlaneGuard
        guard=MaterialControlPlaneGuard(lambda r:__import__('django.http',fromlist=['JsonResponse']).JsonResponse({'ok':True}))
        req=RequestFactory().post('/api/v1/material-sync/imports/',b'x'*(2*1024*1024+1),content_type='application/json')
        self.assertEqual(guard(req).status_code,413)
        req=RequestFactory().post('/api/v1/materials/manage/',b'x'*262145,content_type='application/json')
        self.assertEqual(guard(req).status_code,413)

    @override_settings(MATERIAL_SYNC_RECEIVER_ENABLED=True,MATERIAL_SYNC_ENVIRONMENT_ID='production')
    @patch('material_library.sync_api.authorize',return_value='local-authoring')
    @patch('material_library.sync_api.worker_ready',return_value=True)
    @patch('material_library.sync_api.enqueue')
    @patch('material_library.sync_engine.verify_resources')
    def test_receiver_api_full_roundtrip_and_lost_response_recovery(self,*_):
        factory=APIRequestFactory();s=self.target_snapshot()
        def post(view,data):return view.as_view()(factory.post('/api/v1/material-sync/',data,format='json'))
        pre=post(ReceivePreflight,{'snapshot':s,'storage':wire_environment(),'request_key':'req1'})
        self.assertEqual(pre.status_code,202)
        t=MaterialSyncTask.objects.get(pk=pre.data['id']);receiver_preflight(t,'')
        t.refresh_from_db();self.assertEqual(t.state,'ready')
        data=dict(preflight_id=str(t.pk),idempotency_key='import-1',content_hash=s['content_hash'],target_fingerprint=t.baseline)
        result=post(ReceiveImport,data);self.assertEqual(result.status_code,202)
        it=MaterialSyncTask.objects.get(pk=result.data['id']);it.lease_token='test';it.save();receiver_import(it,'test')
        repeated=post(ReceiveImport,data);self.assertEqual(repeated.data['id'],result.data['id'])
        recovered=ReceiveByKey.as_view()(factory.get('/api/v1/material-sync/'),key='import-1')
        self.assertTrue(recovered.data['found']);self.assertEqual(recovered.data['state'],'succeeded')
        data['content_hash']='0'*64
        conflict=post(ReceiveImport,data);self.assertEqual(conflict.status_code,409)
        self.assertEqual(MaterialLibrary.objects.get(pk=s['library_id']).versions.count(),1)

    def test_shared_material_new_revision_blocks(self):
        s=copy.deepcopy(self.s);s['library_id']=str(uuid.uuid4())
        r=s['revisions'][0];r['name']='新名字';r['sync_revision_key']=digest({k:v for k,v in r.items() if k!='sync_revision_key'});s['items'][0]['sync_revision_key']=r['sync_revision_key'];s['content_hash']=content_hash(s)
        with self.assertRaisesMessage(SyncError,'共享引用'):inspect_target(s)

    def test_source_unknown_result_queries_before_posting(self):
        from .tasks import source_step
        t=MaterialSyncTask.objects.create(side='source',source_environment='local-authoring',library_uuid=self.lib.pk,source_version=1,content_hash=self.s['content_hash'],snapshot=self.s,actor=self.user,state='outcome_unknown',idempotency_key=uuid.uuid4().hex)
        with patch('material_library.tasks.remote',side_effect=[{'found':True,'id':'remote-1'},{'state':'succeeded','commit_status':'committed','result':{'target_version':1}}]) as mock:
            self.assertFalse(source_step(t,''))
        self.assertEqual([c.args[0] for c in mock.call_args_list],['GET','GET'])
        t.refresh_from_db();self.assertEqual(t.state,'succeeded')

    def test_metadata_logging_and_stream_limit(self):
        from .middleware import MaterialControlPlaneGuard
        guard=MaterialControlPlaneGuard(lambda r:__import__('django.http',fromlist=['JsonResponse']).JsonResponse({'ok':True}))
        req=RequestFactory().post('/api/v1/material-sync/imports/',b'{}',content_type='application/json')
        req._stream=__import__('io').BytesIO(b'x'*(2*1024*1024+1));req.META['CONTENT_LENGTH']='0'
        self.assertEqual(guard(req).status_code,413)

    @patch('material_library.sync_engine.verify_resources')
    def test_import_remaps_integer_ids_into_independent_catalog(self,verify):
        s=copy.deepcopy(self.s);old_revision=self.rev.pk
        # Simulate a clean destination with unrelated IDs already allocated.
        self.lib.current=None;self.lib.save();LibraryDraft.objects.all().delete();LibraryItem.objects.all().delete()
        LibraryVersion.objects.all().delete();MaterialLibrary.objects.all().delete();MaterialRevision.objects.all().delete();Material.objects.all().delete();ResourceBlob.objects.all().delete()
        b=ResourceBlob.objects.create(sha256='f'*64,object_key=prefix()+'blobs/decoy',byte_size=10,width=1024,height=1024,mime='image/png')
        decoy=Material.objects.create(source_identity='unrelated',material_type='sticker')
        from .services import revision
        unrelated=revision(decoy,dict(name='已有生产素材',kind='illustration',subcategory='object',keywords=[],aliases=[],sources=[],resource_id=b.pk,thumbnail_id=b.pk))
        t=self.task(s);receiver_import(t,'test')
        target=MaterialLibrary.objects.get(pk=s['library_id']);r=target.current.items.get().revision
        self.assertNotEqual(r.pk,old_revision);self.assertNotEqual(r.pk,unrelated.pk)
        self.assertEqual(str(r.material_id),s['materials'][0]['id']);self.assertEqual(r.resource_id,s['revisions'][0]['resource_sha256'])
        self.assertTrue(Material.objects.filter(pk=decoy.pk).exists())

    @override_settings(MATERIAL_SYNC_ENVIRONMENT_ID='production')
    def test_production_hides_source_sync_action(self):
        from .sync_api import SyncOptions
        req=APIRequestFactory().get('/api/v1/materials/manage/sync/options/')
        force_authenticate(req,user=self.user)
        response=SyncOptions.as_view()(req)
        self.assertFalse(response.data['can_sync'])

    @patch('material_library.tasks.enqueue')
    @patch('material_library.tasks.remote',side_effect=SyncError('TARGET_UNAVAILABLE','network unavailable',True))
    def test_network_failures_stop_after_three_attempts(self,*_):
        from .tasks import run_sync_task
        t=MaterialSyncTask.objects.create(side='source',source_environment='local-authoring',library_uuid=self.lib.pk,source_version=1,content_hash=self.s['content_hash'],snapshot=self.s,actor=self.user,state='preflighting',idempotency_key=uuid.uuid4().hex)
        for _ in range(3):run_sync_task.run(str(t.pk))
        t.refresh_from_db()
        self.assertEqual(t.state,'failed');self.assertEqual(t.attempts,3)
        self.assertTrue(t.result['manual_retry']);self.assertEqual(t.result['network_failures'],3)
