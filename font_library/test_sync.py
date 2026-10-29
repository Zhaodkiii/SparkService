import copy
import time
import uuid
from datetime import timedelta
from unittest.mock import patch,Mock
from django.test import TestCase,override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from billing.models import ContentOffer,ContentPolicyRevision
from .models import *
from .services import normalize
from .sync_protocol import *
from .sync_engine import claim,receiver_preflight,receiver_import
from .sync_transport import signature,remote

@override_settings(FONT_OSS_PREFIX='shared/fonts/',MATERIAL_SYNC_ENVIRONMENT_ID='local-authoring',ALIYUN_OSS_BUCKET='shared',ALIYUN_OSS_ENDPOINT='https://oss-cn-beijing.aliyuncs.com')
class FontSyncTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser(username='font-sync',password='unused',email='')
        self.font=FontFamily.objects.create(title='字体',active=True)
        assets=[]
        for kind,mime in [('font','font/ttf'),('cover','image/png'),('preview','image/png'),('license','text/plain')]:
            assets.append(FontAsset.objects.create(family=self.font,kind=kind,mime=mime,object_key='shared/fonts/candidates/'+str(uuid.uuid4())+'/resource',sha256='a'*64,byte_size=10,metadata={'faces':[{'postscript_name':'Test-Regular'}]} if kind=='font' else {}))
        self.content=normalize(dict(title='字体',faces=[dict(id='regular',asset_id=str(assets[0].pk),postscript_name='Test-Regular',label='Regular')],default_face='regular',cover=str(assets[1].pk),previews=[str(assets[2].pk)],license_asset=str(assets[3].pk),license_approved=True,license_scopes=['app','distribution'],languages=['简体中文']))
        v=FontRelease.objects.create(family=self.font,number=3,content=self.content,digest='a'*64);v.assets.set(assets)
        self.font.current=v;self.font.save();FontDraft.objects.create(family=self.font,content=self.content,base_version=3)
        offer=ContentOffer.objects.create(target_kind='font',target_id=self.font.pk,title='字体',state='active')
        offer.current_policy_revision=ContentPolicyRevision.objects.create(offer=offer,revision=1,access_mode='free');offer.save()
        self.snapshot=snapshot_for(self.font)
    def remove_source(self):
        ContentOffer.objects.filter(target_id=self.font.pk).update(current_policy_revision=None)
        ContentPolicyRevision.objects.all().delete();ContentOffer.objects.all().delete()
        FontDraft.objects.all().delete();FontFamily.objects.filter(pk=self.font.pk).update(current=None)
        FontRelease.objects.all().delete();FontAsset.objects.all().delete();FontFamily.objects.all().delete()
    def task(self):
        return FontSyncTask.objects.create(side='target',library_uuid=self.font.pk,source_environment='local-authoring',source_version=3,content_hash=self.snapshot['content_hash'],snapshot=self.snapshot,idempotency_key=uuid.uuid4().hex)
    @patch('font_library.storage.verify')
    def test_first_import_no_file_body_and_source_version_preserved(self,verify):
        original=[a['object_key'] for a in self.snapshot['resources']]
        self.remove_source();t=self.task();token=claim(t.pk);receiver_preflight(t,token)
        t.refresh_from_db();self.assertEqual(t.state,'ready');self.assertEqual(t.result['next_version'],3)
        receiver_import(t,token);t.refresh_from_db();self.assertEqual(t.state,'succeeded')
        f=FontFamily.objects.get(pk=self.font.pk);self.assertEqual(f.current.number,3)
        self.assertCountEqual(f.current.assets.values_list('object_key',flat=True),original)
        self.assertEqual(verify.call_count,8)
        before=FontRelease.objects.count();receiver_import(t,token);self.assertEqual(FontRelease.objects.count(),before)
        self.assertEqual(ContentOffer.objects.get(target_id=f.pk).current_policy_revision.access_mode,'free')
    @patch('font_library.storage.verify')
    def test_noop_and_production_draft_conflict(self,verify):
        result=inspect_target(self.snapshot);self.assertTrue(result['no_op'])
        d=self.font.fontdraft;d.content={**d.content,'title':'生产未发布修改'};d.save()
        with self.assertRaises(SyncError) as c:inspect_target(self.snapshot)
        self.assertEqual(c.exception.code,'TARGET_DRAFT_CONFLICT')
    def test_rejects_private_paths_bad_hash_missing_refs(self):
        for change in ['path','hash','ref']:
            s=copy.deepcopy(self.snapshot)
            if change=='path':s['resources'][0]['object_key']='private/other/font'
            if change=='hash':s['content_hash']='b'*64
            if change=='ref':s['library']['cover']=str(uuid.uuid4())
            with self.assertRaises(SyncError):validate_snapshot(s)
    @patch('font_library.storage.verify')
    def test_changed_target_between_preflight_and_commit_rolls_back(self,verify):
        t=self.task();token=claim(t.pk);receiver_preflight(t,token)
        FontFamily.objects.filter(pk=self.font.pk).update(state_revision=42)
        with self.assertRaises(SyncError):receiver_import(t,token)
        self.assertEqual(FontRelease.objects.count(),1);t.refresh_from_db();self.assertEqual(t.commit_status,'not_committed')
    @override_settings(DIAMOND_REDEMPTION_ENABLED=False)
    def test_paid_first_import_respects_production_sales_switch(self):
        self.remove_source();s=copy.deepcopy(self.snapshot)
        s['initial_policy'].update(access_mode='diamond_only',diamond_price=10,currency_code='DIAMOND')
        with self.assertRaises(SyncError) as c:inspect_target(s)
        self.assertEqual(c.exception.code,'SALES_DISABLED')
    def test_key_identity_conflict(self):
        FontAsset.objects.filter(pk=self.snapshot['resources'][0]['id']).update(byte_size=50)
        with self.assertRaises(SyncError) as c:inspect_target(self.snapshot)
        self.assertEqual(c.exception.code,'RESOURCE_METADATA_MISMATCH')
    @override_settings(MATERIAL_SYNC_ENVIRONMENT_ID='production',MATERIAL_SYNC_RECEIVER_ENABLED=True,MATERIAL_SYNC_ACCEPTED_KEYS={'test':{'secret':'secret','environment':'local-authoring'}})
    @patch('font_library.sync_api.worker_ready',return_value=True)
    @patch('font_library.sync_api.enqueue')
    def test_hmac_oss_mismatch_replay_and_preflight(self,enqueue,ready):
        client=APIClient();path='/api/v1/font-sync/preflights/'
        body=canonical(dict(snapshot=self.snapshot,storage=wire_environment(),request_key='one'))
        stamp=str(int(time.time()));nonce=uuid.uuid4().hex
        headers=dict(HTTP_X_SYNC_KEY='test',HTTP_X_SYNC_TIME=stamp,HTTP_X_SYNC_NONCE=nonce,HTTP_X_SYNC_SIGNATURE=signature('secret','POST',path,stamp,nonce,body))
        r=client.post(path,body,content_type='application/json',**headers);self.assertEqual(r.status_code,202)
        self.assertEqual(client.post(path,body,content_type='application/json',**headers).status_code,403)
        body=canonical(dict(snapshot=self.snapshot,storage={**wire_environment(),'prefix':'different/'},request_key='two'))
        nonce=uuid.uuid4().hex;headers.update(HTTP_X_SYNC_NONCE=nonce,HTTP_X_SYNC_SIGNATURE=signature('secret','POST',path,stamp,nonce,body))
        self.assertEqual(client.post(path,body,content_type='application/json',**headers).status_code,409)
    @override_settings(MATERIAL_SYNC_SOURCE_ENABLED=True,MATERIAL_SYNC_TARGET_BASE_URL='https://diary.dreamwhale.top',MATERIAL_SYNC_KEY_ID='test',MATERIAL_SYNC_SECRET='secret')
    @patch('font_library.sync_transport.requests.Session')
    def test_transport_uses_font_endpoint_not_sticker_endpoint(self,session):
        response=Mock(status_code=200);response.iter_content.return_value=[b'{"environment":"production"}']
        session.return_value.__enter__.return_value.request.return_value=response
        self.assertEqual(remote('GET','capabilities/')['environment'],'production')
        self.assertEqual(session.return_value.__enter__.return_value.request.call_args.args[1],'https://diary.dreamwhale.top/api/v1/font-sync/capabilities/')

    @patch('font_library.storage.verify')
    def test_higher_source_version_with_same_content_is_not_noop(self,verify):
        s=copy.deepcopy(self.snapshot);s['source_version']=4;s['content_hash']=content_hash(s)
        FontSyncMapping.objects.create(source_environment='local-authoring',library_uuid=self.font.pk,source_version=3,content_hash=self.snapshot['content_hash'],target_version=self.font.current)
        result=inspect_target(s)
        self.assertFalse(result['no_op']);self.assertEqual(result['next_version'],4)

    @patch('font_library.storage.verify')
    def test_existing_production_price_preserved_on_import(self,verify):
        offer=ContentOffer.objects.get(target_id=self.font.pk)
        offer.current_policy_revision.access_mode='diamond_only'
        offer.current_policy_revision.diamond_price=80
        offer.current_policy_revision.currency_code='DIAMOND'
        offer.current_policy_revision.save()
        s=copy.deepcopy(self.snapshot);s['source_version']=4;s['library']['license_scopes'].append('paid_service');s['content_hash']=content_hash(s)
        FontSyncMapping.objects.create(source_environment='local-authoring',library_uuid=self.font.pk,source_version=3,content_hash=self.snapshot['content_hash'],target_version=self.font.current)
        t=self.task();t.snapshot=s;t.source_version=4;t.content_hash=s['content_hash'];t.save()
        token=claim(t.pk);receiver_preflight(t,token);receiver_import(t,token)
        offer.refresh_from_db();self.assertEqual(offer.current_policy_revision.diamond_price,80)
        self.assertEqual(offer.policies.count(),1)

    @patch('font_library.tasks.remote')
    def test_source_recovers_lost_import_response_by_business_key(self,remote):
        from .tasks import source_step
        t=self.task();t.side='source';t.state='outcome_unknown';t.actor=self.user;t.remote_preflight_id=str(uuid.uuid4());t.save()
        remote.side_effect=[{'found':True,'id':'remote-task'},{'state':'succeeded','commit_status':'committed','result':{'target_version':3}}]
        self.assertFalse(source_step(t,'lease'))
        self.assertEqual(t.state,'succeeded')
        self.assertEqual(remote.call_count,2)
        self.assertTrue(all(call.args[0]=='GET' for call in remote.call_args_list))

    @patch('font_library.storage.verify',side_effect=RuntimeError('offline'))
    def test_oss_failure_prevents_target_write(self,verify):
        self.remove_source();t=self.task();token=claim(t.pk)
        with self.assertRaises(SyncError):receiver_preflight(t,token)
        self.assertFalse(FontFamily.objects.exists());self.assertFalse(FontRelease.objects.exists())

    def test_inactive_production_offer_blocks_instead_of_duplicate_creation(self):
        ContentOffer.objects.filter(target_id=self.font.pk).update(state='draft')
        with self.assertRaises(SyncError) as c:inspect_target(self.snapshot)
        self.assertEqual(c.exception.code,'POLICY_REQUIRED')

    def test_verified_local_delivery_paths_supported_without_moving_resources(self):
        s=copy.deepcopy(self.snapshot)
        for a in s['resources']:
            filename='font/font.ttf' if a['kind']=='font' else a['kind']+'.png'
            a['object_key']=f"shared/fonts/deliveries/{s['library_id']}/{a['sha256'][:16]}/{filename}"
        s['content_hash']=content_hash(s)
        validate_snapshot(s)
        # A different family or mismatched digest must still be rejected.
        for change in ['family','digest']:
            bad=copy.deepcopy(s)
            if change=='family':bad['resources'][0]['object_key']=bad['resources'][0]['object_key'].replace(s['library_id'],str(uuid.uuid4()))
            else:bad['resources'][0]['object_key']=bad['resources'][0]['object_key'].replace('a'*16,'b'*16)
            bad['content_hash']=content_hash(bad)
            with self.assertRaises(SyncError):validate_snapshot(bad)
