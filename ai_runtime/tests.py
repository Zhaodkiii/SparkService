import copy
import uuid
from datetime import timedelta
from unittest.mock import patch
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from common.exceptions import APIError
from ai_production.models import ProductionPolicy, ProductionTask, ProductionWindow
from ai_production.services import start, transition, complete, authorize
from . import models as m, services as s
from .contracts import digest, endpoint
from .tasks import PinnedHTTPSConnection, run_test

CAP = {'platform': 'ios', 'app_build': 100, 'contract_version': 1,
       'schema_versions': [1], 'adapter_ids': ['ark_responses_v1', 'ark_images_v1']}


@override_settings(AI_RUNTIME_ENCRYPTION_KEYS=[Fernet.generate_key().decode()],
                   AI_RUNTIME_ALLOWED_HOSTS=['ark.cn-beijing.volces.com'])
class RuntimeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='runtime-user', password='test')
        self.admin = get_user_model().objects.create_superuser(username='runtime-admin', password='test')
        self.api = APIClient(); self.api.force_authenticate(self.admin)
        self.provider = m.Provider.objects.create(name='Ark', host='ark.cn-beijing.volces.com')
        self.slot = m.CredentialSlot.objects.create(provider=self.provider, name='main', active_version=1)
        self.secret = 'test-only-secret-never-real'
        self.v1 = m.CredentialVersion.objects.create(slot=self.slot, version=1, ciphertext=s.encrypt(self.secret),
            fingerprint='test', suffix='real')
        self.model = m.Model.objects.create(provider=self.provider, name='layout', model_id='model-a',
            adapter_id='ark_responses_v1', endpoint='https://ark.cn-beijing.volces.com/api/v3/responses',
            capabilities=['vision', 'tools', 'stream'])
        self.ch = m.Channel.objects.get(pk=1)
        self.ch.draft = {'minimum_build': 1, 'scenes': {'diary.layout': {
            'model': str(self.model.pk), 'credential_slot': str(self.slot.pk), 'parameters': {}, 'timeout_seconds': 180}}}
        self.ch.save()
        ProductionPolicy.objects.create(name='runtime', short_limit_points=10, weekly_limit_points=10, rates={
            'model-a': dict(category='text_ai', mode='tokens', input_rate='1', cached_input_rate='1',
                            output_rate='1', minimum_charge='0.1', max_input_tokens=1000,
                            max_output_tokens=4096, usage_timeout_seconds=420),
        }, reason='test')
        self.release = self.publish()

    def tested(self, snap=None, versions=None):
        snap = snap or s.snapshot(m.Channel.objects.get(pk=1).draft)
        return m.TestRun.objects.create(actor=self.admin, snapshot=snap, config_hash=digest(snap),
            versions=versions or s.versions_for(snap), state='passed')

    def publish(self):
        self.tested()
        ch=m.Channel.objects.get(pk=1)
        return s.publish(self.admin, {'request_key':str(uuid.uuid4()),'expected_channel_version':ch.version,
            'expected_draft_revision':ch.revision,'reason':'test'})

    def make(self, key=None, required=None):
        return start(self.user, key or uuid.uuid4(), 'a'*64, CAP, required or ['diary.layout'])

    def config(self, task):
        return s.configuration(self.user, task.pk, CAP, uuid.uuid4())

    def test_encrypt_not_plaintext(self):
        self.assertNotIn(self.secret, self.v1.ciphertext)
        self.assertEqual(s.decrypt(self.v1), self.secret)
        with override_settings(AI_RUNTIME_ENCRYPTION_KEYS=[]):
            with self.assertRaises(APIError): s.encrypt('another-test-secret')

    def test_configuration_is_task_scoped_and_no_store(self):
        task=self.make(); self.api.force_authenticate(self.user)
        response=self.api.post(f'/api/v1/ai-runtime/tasks/{task.pk}/configuration/', {'request_id':str(uuid.uuid4()), 'client_capabilities':CAP}, format='json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Cache-Control'],'no-store')
        self.assertEqual(response.data['data']['credentials'][str(self.slot.pk)]['secret'],self.secret)
        self.assertNotIn(self.secret, str(list(m.Delivery.objects.values())))

    def test_foreign_task_and_closed_task_rejected(self):
        task=self.make()
        with self.assertRaises(APIError): s.configuration(self.admin,task.pk,CAP,uuid.uuid4())
        transition(self.user,task.pk,'cancel',task.version)
        with self.assertRaises(APIError): self.config(task)

    def test_pause_resume(self):
        task=self.make(); paused=transition(self.user,task.pk,'pause',task.version)
        with self.assertRaises(APIError):self.config(task)
        transition(self.user,task.pk,'resume',paused.version)
        self.assertEqual(self.config(task)['task_id'],str(task.pk))

    def test_new_release_does_not_change_existing_task(self):
        task=self.make()
        self.model.model_id='model-b';self.model.save()
        newer=self.publish()
        self.assertNotEqual(newer.pk,self.release.pk)
        self.assertEqual(self.config(task)['scenes']['diary.layout']['model_id'],'model-a')
        self.assertEqual(self.config(self.make())['scenes']['diary.layout']['model_id'],'model-b')

    def test_invalid_configuration_never_reserves(self):
        m.Channel.objects.filter(pk=1).update(enabled=False)
        with self.assertRaises(APIError):self.make()
        self.assertFalse(ProductionTask.objects.exists())
        self.assertFalse(ProductionWindow.objects.exists())

    def test_required_scene_and_capability_validation(self):
        with self.assertRaises(APIError):self.make(required=['diary.background.generate'])
        with self.assertRaises(APIError):start(self.user,uuid.uuid4(),'a'*64,{**CAP,'adapter_ids':[]},['diary.layout'])
        self.assertFalse(ProductionWindow.objects.exists())

    def test_attempt_idempotency_and_scene_conflict(self):
        key=uuid.uuid4();task=self.make(key)
        self.assertEqual(task.pk,self.make(key).pk)
        with self.assertRaises(APIError):self.make(key,['diary.background.generate'])
        self.assertFalse(ProductionWindow.objects.exists())

    def test_emergency_control_affects_old_bindings(self):
        task=self.make(); m.Channel.objects.filter(pk=1).update(disabled_scenes=['diary.layout'])
        with self.assertRaises(APIError):self.config(task)

    def test_disabled_slot_cannot_be_delivered(self):
        task=self.make();m.CredentialSlot.objects.filter(pk=self.slot.pk).update(enabled=False)
        with self.assertRaises(APIError):self.config(task)

    def test_bad_endpoints_and_parameters(self):
        for url in ('http://ark.cn-beijing.volces.com/a','https://127.0.0.1/a','https://ark.cn-beijing.volces.com/a?key=secret','https://user@ark.cn-beijing.volces.com/a'):
            with self.assertRaises(APIError):endpoint(url)
        draft=copy.deepcopy(self.ch.draft);draft['scenes']['diary.layout']['parameters']={'headers':{'Authorization':'anything'}}
        with self.assertRaises(APIError):s.snapshot(draft)

    def test_missing_capabilities_blocks_publish(self):
        self.model.capabilities=['vision'];self.model.save()
        with self.assertRaises(APIError):s.snapshot(self.ch.draft)

    def test_publish_requires_fresh_exact_test(self):
        m.TestRun.objects.all().delete()
        with self.assertRaises(APIError):s.publish(self.admin,{'request_key':str(uuid.uuid4()),'expected_channel_version':2,'expected_draft_revision':1,'reason':'test'})
        self.assertEqual(m.Release.objects.count(),1)

    def test_publish_idempotency_and_conflict(self):
        data={'request_key':str(uuid.uuid4()),'expected_channel_version':2,'expected_draft_revision':1,'reason':'test'}
        first=s.publish(self.admin,data);self.assertEqual(s.publish(self.admin,data).pk,first.pk)
        with self.assertRaises(APIError):s.publish(self.admin,{**data,'reason':'changed'})

    def test_credentials_absent_from_admin_and_manifest(self):
        for path in ['credential-slots/','credential-slots/'+str(self.slot.pk)+'/versions/','releases/','audits/']:
            response=self.api.get('/api/admin/v1/ai-runtime/'+path)
            self.assertEqual(response.status_code,200)
            self.assertNotIn(self.secret,str(response.data))
            self.assertNotIn(self.v1.ciphertext,str(response.data))
        response=self.api.get('/api/v1/ai-runtime/manifest/')
        self.assertNotIn(self.secret,str(response.data))

    def test_non_admin_write_forbidden(self):
        self.api.force_authenticate(self.user)
        response=self.api.post('/api/admin/v1/ai-runtime/providers/',{'name':'x','host':'ark.cn-beijing.volces.com'},format='json')
        self.assertEqual(response.status_code,403)

    def test_rotation_does_not_change_release(self):
        task=self.make()
        m.CredentialVersion.objects.create(slot=self.slot,version=2,ciphertext=s.encrypt('new-test-only-secret'),fingerprint='v2',suffix='cret')
        snap=s.snapshot(self.ch.draft);self.tested(snap,{str(self.slot.pk):2})
        response=self.api.post(f'/api/admin/v1/ai-runtime/credential-slots/{self.slot.pk}/activate/',
            {'version':2,'expected_version':1,'request_key':str(uuid.uuid4()),'reason':'rotate'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        value=self.config(task)
        self.assertEqual(value['release_id'],str(self.release.pk))
        self.assertEqual(value['credentials'][str(self.slot.pk)]['version'],2)

    def test_unverified_rotation_rejected(self):
        m.CredentialVersion.objects.create(slot=self.slot,version=2,ciphertext=s.encrypt('new-test-only-secret'),fingerprint='v2',suffix='cret')
        response=self.api.post(f'/api/admin/v1/ai-runtime/credential-slots/{self.slot.pk}/activate/',
            {'version':2,'expected_version':1,'request_key':str(uuid.uuid4()),'reason':'rotate'},format='json')
        self.assertEqual(response.status_code,422)

    def test_old_client_cannot_start_unmetered_task(self):
        self.api.force_authenticate(self.user)
        response = self.api.post('/api/v1/ai-production/tasks/', {
            'attempt_key': str(uuid.uuid4()), 'input_digest': 'a' * 64,
            'required_scenes': ['diary.layout'], 'client_capabilities': CAP,
        }, format='json')
        self.assertEqual(response.status_code, 426)

    def test_complete_records_result_without_deducting_quota(self):
        task = self.make()
        authorize(self.user, task.pk, uuid.uuid4(), 'diary.layout', 'b' * 64, {'max_output_tokens': 4096})
        complete(self.user, task.pk, {'digest': 'b' * 64})
        complete(self.user, task.pk, {'digest': 'b' * 64})
        self.assertEqual(list(ProductionWindow.objects.values_list('used_points', flat=True)), [0, 0])
        with self.assertRaises(APIError):
            self.config(task)

    def test_metered_task_authorization_and_report(self):
        self.api.force_authenticate(self.user)
        response = self.api.post('/api/v1/ai-production/tasks/', {
            'usage_metering': True, 'attempt_key': str(uuid.uuid4()), 'input_digest': 'a' * 64,
            'required_scenes': ['diary.layout'], 'client_capabilities': CAP,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        root = f"/api/v1/ai-production/tasks/{response.data['data']['id']}/calls/"
        call_id = str(uuid.uuid4())
        inputs = {'call_id': call_id, 'scene': 'diary.layout', 'input_digest': 'b' * 64,
                  'parameters': {'max_output_tokens': 4096}}
        self.assertEqual(self.api.post(root, inputs, format='json').status_code, 200)
        self.assertEqual(self.api.post(root, inputs, format='json').status_code, 200)
        self.assertEqual(self.api.post(root, dict(inputs, call_id=str(uuid.uuid4())), format='json').status_code, 409)
        response = self.api.post(root + call_id + '/usage/', {
            'event_id': str(uuid.uuid4()), 'execution_state': 'completed',
            'usage': {'input_tokens': 500, 'output_tokens': 500},
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([w['remaining_ratio'] for w in response.data['data']['quota']['windows']], [0.9, 0.9])

    @override_settings(AI_RUNTIME_TEST_DOH_FALLBACK=False)
    def test_probe_rejects_private_dns_before_connection(self):
        with patch('ai_runtime.tasks.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]), patch('ai_runtime.tasks.socket.create_connection') as connect:
            with self.assertRaises(ValueError):PinnedHTTPSConnection('ark.cn-beijing.volces.com').connect()
            connect.assert_not_called()

    def test_worker_duplicate_delivery_does_not_repeat_probe(self):
        run=self.tested();run.state='queued';run.save()
        with patch('ai_runtime.tasks.probe',return_value={'passed':True,'code':'OK'}) as probe:
            run_test(str(run.pk));run_test(str(run.pk))
            self.assertEqual(probe.call_count,1)

    def test_draft_conflict_does_not_overwrite(self):
        response=self.api.put('/api/admin/v1/ai-runtime/drafts/current/',{'expected_revision':99,'draft':self.ch.draft},format='json')
        self.assertEqual(response.status_code,409)

    def test_rollback_creates_new_release(self):
        self.model.model_id='model-b';self.model.save();self.publish()
        ch=m.Channel.objects.get(pk=1)
        result=s.publish(self.admin,{'request_key':str(uuid.uuid4()),'expected_channel_version':ch.version,
            'expected_draft_revision':ch.revision,'reason':'rollback','rollback_id':str(self.release.pk)},self.release)
        self.assertEqual(result.snapshot,self.release.snapshot)
        self.assertNotEqual(result.pk,self.release.pk)
