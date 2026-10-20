import importlib
import json
import time
from datetime import timedelta
from unittest.mock import patch
from types import SimpleNamespace
from django.apps import apps
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from diary_customizations import tests as fixtures
from diary_customizations.models import Delivery
from .models import ResourceTask, Series, Template, Upload
from .resource_queue import enqueue
from .tests import snapshot


@override_settings(DIARY_PRESETS_PROCESSOR_TOKEN='queue-secret')
class SingleQueueTests(TestCase):
    setUp = fixtures.CustomizationTests.setUp
    candidate = fixtures.CustomizationTests.candidate
    asset = fixtures.CustomizationTests.asset

    def public(self):
        series, _ = Series.objects.get_or_create(slug='public-test', defaults={'title':'public'})
        template = Template.objects.create(series=series, title='public')
        return Upload.objects.create(template=template, actor=self.admin, revision=0,
            object_key='traveldiary/presets/staging/test/source.zip', size=1, status='queued')

    def private(self):
        delivery = self.candidate()
        job = delivery.job
        delivery.delete()
        job.status = 'queued'
        job.save()
        return job

    def post(self, data):
        self.client.force_authenticate(None)
        return self.client.post('/api/internal/diary-presets/processor/', data,
            format='json', HTTP_X_PRESET_PROCESSOR='queue-secret')

    def test_public_and_private_share_fifo_and_no_second_claim_endpoint(self):
        private = self.private(); public = self.public()
        first = enqueue(private); second = enqueue(public)
        a = self.post({'action':'claim'}); b = self.post({'action':'claim'})
        self.assertEqual(a.data['id'], str(first.pk)); self.assertEqual(a.data['resource_type'], 'customization')
        self.assertEqual(b.data['id'], str(second.pk)); self.assertEqual(b.data['resource_type'], 'public')
        self.assertEqual(self.post({'action':'claim'}).status_code, 204)
        old = self.client.post('/api/internal/diary-customizations/processor/', {'action':'claim'},
            format='json', HTTP_X_PRESET_PROCESSOR='queue-secret')
        self.assertEqual(old.status_code, 410)

    def test_retry_reuses_queue_record_and_moves_to_tail(self):
        source = self.public(); task = enqueue(source)
        task.status='done'; task.save(); before=task.created_at
        next_task=enqueue(self.public()); retried=enqueue(source)
        self.assertEqual(retried.pk, task.pk); self.assertEqual(ResourceTask.objects.count(), 2)
        self.assertGreater(retried.created_at, before)
        self.assertEqual(self.post({'action':'claim'}).data['id'], str(next_task.pk))

    def test_photos_cannot_enter_queue(self):
        photo=self.asset()
        with self.assertRaises(ValueError): enqueue(photo.job)
        self.assertEqual(ResourceTask.objects.count(), 0)

    def test_cancelled_request_is_never_claimed(self):
        j=self.private(); enqueue(j)
        self.r.status='cancelled'; self.r.save()
        self.assertEqual(self.post({'action':'claim'}).status_code,204)

    def test_expired_lease_reclaims_once_and_rejects_old_report(self):
        task=enqueue(self.public()); first=self.post({'action':'claim'}).data
        ResourceTask.objects.filter(pk=task.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
        second=self.post({'action':'claim'}).data
        self.assertNotEqual(first['lease'],second['lease'])
        self.assertEqual(self.post({**first,'error':'failed'}).status_code,409)
        self.assertEqual(self.post({**second,'error':'failed'}).status_code,200)
        task.refresh_from_db(); self.assertEqual(task.status,'done')
        task.upload.refresh_from_db(); self.assertEqual(task.upload.status,'failed')

    def test_private_success_only_creates_candidate_and_duplicate_report_is_idempotent(self):
        j=self.private(); task=enqueue(j); claim=self.post({'action':'claim'}).data
        result=snapshot(); result['manifest']['packageVersion']=1
        prefix=f'traveldiary/customizations/{self.r.owner_id}/{self.r.pk}/blobs/'
        result['keys']={path:prefix+path for path in result['keys']}
        count=Delivery.objects.count()
        for _ in range(2):
            answer=self.post({'id':claim['id'],'lease':claim['lease'],'result':result})
            self.assertEqual(answer.status_code,200,answer.data)
        self.assertEqual(Delivery.objects.count(),count+1)
        j.refresh_from_db(); self.assertEqual(j.status,'ready')
        self.r.refresh_from_db(); self.assertEqual(self.r.status,'in_production')
        task.refresh_from_db();self.assertEqual(task.status,'done')

    def test_migration_imports_existing_public_and_delivery_but_no_photos(self):
        self.public();self.private();photo=self.asset();photo.job.status='queued';photo.job.save()
        migration=importlib.import_module('diary_presets.migrations.0003_resourcetask')
        migration.import_pending(apps,SimpleNamespace(connection=connection))
        self.assertEqual(ResourceTask.objects.count(),2)

    def test_runtime_counts_single_queue_and_requires_new_worker_protocol(self):
        enqueue(self.public());enqueue(self.private())
        self.asset()
        from .processor_runtime import runtime_status
        heartbeat={'pid':123,'updated_at':time.time(),'connected':True,'protocol_version':3}
        with patch('scripts.runtime.pid_for',return_value=123),patch('scripts.runtime.owned',return_value=True),patch('pathlib.Path.read_text',return_value=json.dumps(heartbeat)),patch('diary_presets.processor_runtime.configuration_error',return_value=''):
            result=runtime_status()
        self.assertEqual((result['queued'],result['processing']),(2,0));self.assertTrue(result['healthy'])
        self.assertNotIn('queues',result);self.assertNotIn('customization_queued',result)
