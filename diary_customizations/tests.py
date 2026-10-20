import uuid
from unittest.mock import patch,MagicMock
from django.contrib.auth import get_user_model
from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from diary_presets.models import Template,Series,Version,DownloadPlan
from diary_presets.tests import snapshot
from notification_center.models import NotificationIntent,NotificationOutbox
from .models import Request,Asset,Job,Submission,Delivery

class CustomizationTests(TestCase):
    def setUp(self):
        User=get_user_model();self.a=User.objects.create_user(username='owner');self.b=User.objects.create_user(username='other')
        self.admin=User.objects.create_superuser(username='designer',email='designer@example.test',password='x')
        self.client=APIClient();self.client.force_authenticate(self.a)
        self.r=Request.objects.create(owner=self.a,creation_key=uuid.uuid4(),title='私人主题',brief={'description':'故事'})
    def action(self,name,data=None,admin=False,key=None):
        self.r.refresh_from_db();self.client.force_authenticate(self.admin if admin else self.a)
        url=('/api/admin/v1/' if admin else '/api/v1/')+'diary-customizations/requests/'+str(self.r.pk)+'/'+name+'/'
        return self.client.post(url,{'expected_revision':self.r.revision,**(data or {})},format='json',HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))
    def asset(self):
        a=Asset.objects.create(request=self.r,client_id=uuid.uuid4(),size=1,sha256='a'*64,mime='image/jpeg',status='ready')
        Job.objects.create(request=self.r,actor=self.a,asset=a,kind='asset',size=1,sha256='a'*64,object_key='staging')
        return a
    def candidate(self):
        sub=Submission.objects.create(request=self.r,number=1,snapshot={'assets':[]})
        self.r.accepted_submission=sub;self.r.status='in_production';self.r.save()
        series=Series.objects.create(slug='private-custom',title='private',active=False)
        t=Template.objects.create(series=series,title='private',audience='private',owner=self.a,customization_id=self.r.pk)
        snap=snapshot()
        for p in snap['pages']:p['data']['preview']={'thumbnailPath':'shared.png','largePath':'shared.png'}
        snap['manifest']['title']='private'
        v=Version.objects.create(template=t,number=1,snapshot=snap)
        t.current=v;t.save()
        job=Job.objects.create(request=self.r,actor=self.admin,submission=sub,kind='delivery',size=1,sha256='b'*64,object_key='staging')
        return Delivery.objects.create(request=self.r,submission=sub,job=job,version=v,number=1)
    def test_create_is_idempotent(self):
        key=str(uuid.uuid4());url='/api/v1/diary-customizations/requests/'
        a=self.client.post(url,{'creation_key':key},format='json');b=self.client.post(url,{'creation_key':key},format='json')
        self.assertEqual(a.data['id'],b.data['id'])
    def test_other_account_cannot_read_or_mutate(self):
        self.client.force_authenticate(self.b)
        for method in ('get','patch'):
            self.assertEqual(getattr(self.client,method)(f'/api/v1/diary-customizations/requests/{self.r.pk}/').status_code,404)
    def test_submit_requires_ready_images(self):
        self.assertEqual(self.action('submit').status_code,400)
        a=self.asset();a.status='uploading';a.save()
        self.assertEqual(self.action('submit').status_code,400)
    def test_submission_is_immutable_and_retries_do_not_duplicate(self):
        self.asset();self.r.refresh_from_db();rev=self.r.revision;key=str(uuid.uuid4())
        url=f'/api/v1/diary-customizations/requests/{self.r.pk}/submit/'
        for _ in range(2): self.assertEqual(self.client.post(url,{'expected_revision':rev},format='json',HTTP_IDEMPOTENCY_KEY=key).status_code,200)
        self.assertEqual(self.r.submissions.count(),1)
        self.assertEqual(self.action('submit').status_code,409)
    def test_non_admin_cannot_accept(self): self.assertEqual(self.action('accept').status_code,400)
    def test_admin_accepts_submitted_snapshot_and_repeating_same_operation_is_idempotent(self):
        self.asset()
        self.assertEqual(self.action('submit').status_code,200)
        sub=self.r.submissions.get()
        self.r.refresh_from_db();revision=self.r.revision
        self.client.force_authenticate(self.admin)
        url=f'/api/admin/v1/diary-customizations/requests/{self.r.pk}/accept/'
        body={'expected_revision':revision,'submission_id':sub.pk,'message':''}
        for _ in range(2):
            response=self.client.post(url,body,format='json',HTTP_IDEMPOTENCY_KEY='accept-once',HTTP_ORIGIN='http://localhost:6018')
            self.assertEqual(response.status_code,200,response.data)
            self.assertEqual(response.data['status'],'in_production')
        self.r.refresh_from_db()
        self.assertEqual(self.r.accepted_submission_id,sub.pk)
        self.assertEqual(self.r.assigned_to_id,self.admin.pk)
        self.assertEqual(self.r.events.filter(action='accepted').count(),1)
    def test_public_catalog_never_lists_private(self):
        self.candidate()
        with patch('diary_presets.storage.sign',return_value='https://example.test'):
            result=self.client.get('/api/v1/diary-presets/catalog/');self.assertEqual(result.data['books'],[])
    def test_owner_cannot_read_unreleased_candidate(self):
        d=self.candidate()
        self.assertEqual(self.client.get(f'/api/v1/diary-presets/templates/{d.version.template_id}/1/').status_code,404)
    def test_deliver_requires_ios_review(self):
        d=self.candidate()
        self.assertEqual(self.action('deliver',{'delivery_id':str(d.pk)},True).status_code,400)
    def test_deliver_outbox_atomic_and_private_download_revoked(self):
        d=self.candidate()
        with patch('diary_customizations.storage.sign',return_value='https://example.test'):
            response=self.action('deliver',{'delivery_id':str(d.pk),'ios_reviewed':True,'used_asset_ids':[]},True)
            self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(NotificationOutbox.objects.count(),1);self.assertEqual(NotificationIntent.objects.count(),1)
        url=f'/api/v1/diary-presets/templates/{d.version.template_id}/1/'
        self.client.force_authenticate(self.a);response=self.client.post(url,{},format='json');self.assertEqual(response.status_code,201)
        plan=response.data['id'];d.status='withdrawn';d.save()
        self.assertEqual(self.client.post(f'/api/v1/diary-presets/plans/{plan}/urls/',{'paths':['b.json']},format='json').status_code,404)
        self.client.force_authenticate(self.b);self.assertEqual(self.client.get(url).status_code,404)
    def test_candidate_versions_do_not_consume_published_delivery_number(self):
        d=self.candidate();d.number=5;d.save()
        with patch('diary_customizations.storage.sign',return_value='https://example.test'):
            result=self.action('deliver',{'delivery_id':str(d.pk),'ios_reviewed':True,'used_asset_ids':[]},True)
        self.assertEqual(result.status_code,200);d.refresh_from_db();self.assertEqual(d.published_number,1)
    def test_cancelled_request_cannot_deliver(self):
        d=self.candidate();self.r.status='cancelled';self.r.save()
        self.assertEqual(self.action('deliver',{'delivery_id':str(d.pk),'ios_reviewed':True,'used_asset_ids':[]},True).status_code,409)
    def test_read_cannot_skip_future_sequence(self):
        self.assertEqual(self.client.post(f'/api/v1/diary-customizations/requests/{self.r.pk}/read/',{'sequence':99},format='json').status_code,400)
    def test_asset_upload_quota_is_reserved(self):
        self.r.status='in_production';self.r.save()
        response=self.client.post(f'/api/v1/diary-customizations/requests/{self.r.pk}/uploads/',{'client_id':str(uuid.uuid4()),'size':1,'sha256':'a'*64,'mime':'image/jpeg'},format='json')
        self.assertEqual(response.status_code,409)
    def test_preferences_are_user_scoped(self):
        url='/api/v1/diary-customizations/preferences/'
        self.assertEqual(self.client.patch(url,{'enabled':False},format='json').status_code,200)
        self.client.force_authenticate(self.b);self.assertTrue(self.client.get(url).data['enabled'])
    @override_settings(DIARY_PRESETS_PROCESSOR_TOKEN='processor-secret')
    def test_stale_processing_callback_cannot_revive_deleted_asset(self):
        a=self.asset();a.deleted_at=__import__('django.utils.timezone',fromlist=['now']).now();a.save()
        j=a.job;j.status='processing';j.lease=uuid.uuid4();j.lease_until=a.deleted_at+__import__('datetime').timedelta(minutes=10);j.save()
        self.client.force_authenticate(None)
        r=self.client.post('/api/internal/diary-customizations/processor/',{'id':str(j.pk),'lease':str(j.lease),'result':{}},format='json',HTTP_X_PRESET_PROCESSOR='processor-secret')
        self.assertEqual(r.status_code,200);j.refresh_from_db();self.assertEqual(j.status,'abandoned')

class CustomNotificationTests(TestCase):
    setUp=CustomizationTests.setUp
    action=CustomizationTests.action
    candidate=CustomizationTests.candidate
    def delivered_event(self):
        d=self.candidate()
        with patch('diary_customizations.storage.sign',return_value='https://example.test'):
            response=self.action('deliver',{'delivery_id':str(d.pk),'ios_reviewed':True,'used_asset_ids':[]},True)
            self.assertEqual(response.status_code,200)
        from .models import Event
        e=Event.objects.get(action='delivered');return e,NotificationIntent.objects.get(event_id=str(e.pk))
    @patch('accounts.infrastructure.apns_provider.APNsProvider.send')
    @patch('accounts.services.device_session_service.DeviceSessionService.apns_trusted_device_for_user')
    def test_transient_error_retries_existing_delivery_with_new_attempt(self,device,send):
        from types import SimpleNamespace
        from notification_center.models import ChannelDelivery,DeliveryAttempt
        from .tasks import dispatch_notification
        event,intent=self.delivered_event()
        device.return_value=SimpleNamespace(push_token='token',bundle_identifier='cn.zhaodk.TravelDiary',bundle_id='cn.zhaodk.TravelDiary')
        send.side_effect=[(False,'ServiceUnavailable',''),(True,'','accepted-id')]
        dispatch_notification.run(intent.pk,str(event.pk))
        box=NotificationOutbox.objects.get();self.assertEqual(box.status,'pending')
        ChannelDelivery.objects.update(next_retry_at=None)
        dispatch_notification.run(intent.pk,str(event.pk));box.refresh_from_db()
        self.assertEqual(box.status,'processed');self.assertEqual(DeliveryAttempt.objects.count(),2)
        from notification_center.models import NotificationMessage
        self.assertEqual(NotificationMessage.objects.get().success_count,1)
        dispatch_notification.run(intent.pk,str(event.pk));self.assertEqual(send.call_count,2)
    @patch('accounts.infrastructure.apns_provider.APNsProvider.send')
    def test_revoked_or_superseded_delivery_never_pushes(self,send):
        from .tasks import dispatch_notification
        event,intent=self.delivered_event();self.r.current_delivery=None;self.r.save()
        dispatch_notification.run(intent.pk,str(event.pk))
        self.assertEqual(NotificationOutbox.objects.get().last_error,'superseded');send.assert_not_called()
    @patch('accounts.infrastructure.apns_provider.APNsProvider.send')
    @patch('notification_center.services.NotificationCenterService._suppression_reason',return_value='quiet_hours')
    def test_quiet_hours_defers_without_dropping_business_event(self,suppression,send):
        from .tasks import dispatch_notification
        event,intent=self.delivered_event();dispatch_notification.run(intent.pk,str(event.pk))
        box=NotificationOutbox.objects.get();self.assertEqual(box.status,'pending');self.assertEqual(box.last_error,'deferred_quiet_hours')
        self.assertTrue(self.r.events.filter(pk=event.pk).exists());send.assert_not_called()
    def test_private_source_rejected_by_public_parser_before_upload(self):
        import tempfile,zipfile,json
        from pathlib import Path
        from diary_presets.package import process_archive
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'private.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('package.json',json.dumps({'audience':'private','customizationRequestID':str(self.r.pk)}))
            put=MagicMock()
            with self.assertRaisesRegex(ValueError,'Private packages'):process_archive(archive,Path(tmp)/'expanded','test',put)
            put.assert_not_called()

class AssetLifecycleTests(TestCase):
    setUp=CustomizationTests.setUp
    def upload(self):
        url=f'/api/v1/diary-customizations/requests/{self.r.pk}/uploads/'
        with patch('diary_customizations.storage.upload',side_effect=lambda j:{'id':str(j.pk),'status':j.status,'put_url':'https://test.oss-cn-beijing.aliyuncs.com/photo'}):
            r=self.client.post(url,{'client_id':str(uuid.uuid4()),'size':7,'sha256':'a'*64,'mime':'image/jpeg','width':2,'height':3},format='json')
        self.assertEqual(r.status_code,201)
        return Job.objects.get(pk=r.data['id'])

    def complete(self,job):
        return self.client.post(f'/api/v1/diary-customizations/uploads/{job.pk}/complete/',{},format='json')

    @patch('diary_presets.storage.bucket',side_effect=AssertionError('Photo completion must not access OSS'))
    @patch('diary_customizations.storage.sign',return_value='https://test.oss-cn-beijing.aliyuncs.com/photo')
    def test_upload_completion_is_immediate_idempotent_and_needs_no_storage_io(self,sign,bucket):
        from .storage import scope
        job=self.upload()
        self.assertTrue(job.object_key.startswith(scope(self.r)+'inputs/'))
        for _ in range(2):
            response=self.complete(job)
            self.assertEqual(response.status_code,200,response.data)
            self.assertEqual(response.data['status'],'ready')
        job.refresh_from_db();asset=job.asset
        self.assertEqual(job.status,'ready');self.assertEqual(asset.status,'ready')
        self.assertEqual(asset.object_key,job.object_key)
        self.assertEqual((asset.width,asset.height),(2,3));self.assertEqual(asset.size,7)
        self.assertEqual(asset.thumbnail_key,'');self.assertEqual(asset.sha256,'a'*64)
        detail=self.client.get(f'/api/v1/diary-customizations/requests/{self.r.pk}/').data
        self.assertEqual(detail['assets'][0]['thumbnail_url'],detail['assets'][0]['url'])
        response=self.client.post(f'/api/v1/diary-customizations/requests/{self.r.pk}/submit/',{'expected_revision':1},format='json',HTTP_IDEMPOTENCY_KEY='submit')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(Submission.objects.get(request=self.r).snapshot['assets'][0]['sha256'],'a'*64)
        self.assertEqual(self.client.post(f'/api/v1/diary-customizations/uploads/{job.pk}/refresh/',{},format='json').status_code,409)
        bucket.assert_not_called()

    @override_settings(DIARY_PRESETS_PROCESSOR_TOKEN='processor-secret')
    def test_photo_jobs_are_never_claimed_and_stale_worker_cannot_replace_object(self):
        from django.utils import timezone
        from datetime import timedelta
        for status in ('queued','processing'):
            job=self.upload();job.status=status;job.lease=uuid.uuid4();job.lease_until=timezone.now()+timedelta(minutes=30);job.save()
        self.client.force_authenticate(None)
        url='/api/internal/diary-presets/processor/'
        claim=self.client.post(url,{'action':'claim'},format='json',HTTP_X_PRESET_PROCESSOR='processor-secret')
        self.assertEqual(claim.status_code,204)
        delivery=CustomizationTests.candidate(self)
        Job.objects.filter(pk=delivery.job_id).update(status='queued')
        delivery.job.refresh_from_db()
        from diary_presets.resource_queue import enqueue
        enqueue(delivery.job)
        claim=self.client.post(url,{'action':'claim'},format='json',HTTP_X_PRESET_PROCESSOR='processor-secret')
        self.assertEqual(claim.status_code,200)
        self.assertEqual(claim.data['kind'],'delivery');self.assertEqual(claim.data['source_id'],str(delivery.job_id))
        response=self.client.post('/api/internal/diary-customizations/processor/',{'id':str(job.pk),'lease':str(job.lease),'result':{'object_key':'replacement'}},format='json',HTTP_X_PRESET_PROCESSOR='processor-secret')
        self.assertEqual(response.status_code,409)
        job.refresh_from_db();self.assertEqual(job.asset.object_key,'')

    @patch('diary_presets.storage.bucket',side_effect=AssertionError('Legacy completion must not access OSS'))
    def test_legacy_pending_or_failed_photo_can_finish_without_worker(self,bucket):
        for status in ('queued','processing','failed'):
            job=self.upload();job.status=status;job.error='legacy failure';job.save()
            response=self.complete(job)
            self.assertEqual(response.status_code,200,response.data)
            job.refresh_from_db();self.assertEqual(job.status,'ready');self.assertEqual(job.error,'')
            self.assertEqual(job.asset.object_key,job.object_key)
        bucket.assert_not_called()

    def test_photo_completion_still_checks_owner_deleted_asset_and_request_state(self):
        job=self.upload()
        self.client.force_authenticate(self.b);self.assertEqual(self.complete(job).status_code,404)
        self.client.force_authenticate(self.a)
        self.r.status='cancelled';self.r.save();self.assertEqual(self.complete(job).status_code,409)
        self.r.status='draft';self.r.save()
        from django.utils import timezone
        job.asset.deleted_at=timezone.now();job.asset.save()
        self.assertEqual(self.complete(job).status_code,409)
        job.refresh_from_db();self.assertEqual(job.status,'uploading')

    @patch('diary_presets.storage.bucket')
    def test_signed_photo_put_is_local_only_and_cannot_overwrite(self,bucket):
        from .storage import upload
        job=self.upload();bucket.return_value.sign_url.return_value='https://signed.test'
        response=upload(job)
        self.assertEqual(response['put_headers']['x-oss-forbid-overwrite'],'true')
        self.assertEqual(response['put_headers']['Content-Type'],'image/jpeg')
        bucket.return_value.head_object.assert_not_called();bucket.return_value.get_object.assert_not_called()
        bucket.return_value.put_object.assert_not_called();bucket.return_value.copy_object.assert_not_called()
        self.assertEqual(bucket.return_value.sign_url.call_args.kwargs['headers'],response['put_headers'])
        self.complete(job);job.refresh_from_db()
        self.assertNotIn('put_url',upload(job))

    @patch('diary_presets.storage.bucket',side_effect=AssertionError('Migration must not access OSS'))
    def test_data_migration_releases_old_photo_jobs_without_touching_files(self,bucket):
        from django.apps import apps
        from django.db import connection
        from importlib import import_module
        from types import SimpleNamespace
        from django.utils import timezone
        jobs=[]
        for status in ('queued','processing','failed','uploading'):
            job=self.upload();job.status=status;job.save();jobs.append(job)
        removed=self.upload();removed.status='queued';removed.save()
        Asset.objects.filter(pk=removed.asset_id).update(deleted_at=timezone.now())
        run=import_module('diary_customizations.migrations.0004_direct_photo_upload').finish_legacy_photo_jobs
        for _ in range(2):run(apps,SimpleNamespace(connection=connection))
        for job in jobs:
            job.refresh_from_db()
            self.assertEqual(job.status,'uploading' if job==jobs[-1] else 'ready')
            if job.status=='ready':self.assertEqual(job.asset.object_key,job.object_key)
        removed.refresh_from_db();self.assertEqual(removed.status,'abandoned')
        bucket.assert_not_called()

    @patch('diary_customizations.management.commands.cleanup_customizations.bucket')
    def test_cleanup_never_deletes_ready_photo_as_one_day_old_staging(self,bucket):
        from django.core.management import call_command
        from django.utils import timezone
        from datetime import timedelta
        from io import StringIO
        job=self.upload();self.complete(job)
        Job.objects.filter(pk=job.pk).update(created_at=timezone.now()-timedelta(days=2))
        call_command('cleanup_customizations',execute=True,stdout=StringIO())
        bucket.return_value.delete_object.assert_not_called()
        job.refresh_from_db();self.assertEqual(job.status,'ready')
