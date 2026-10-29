import base64
from unittest.mock import patch, Mock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from django.utils import timezone
from datetime import timedelta
from .models import *
from . import services
from billing.models import ContentOffer, ContentPolicyRevision

@override_settings(FONT_PROCESSOR_TOKEN='test-processor',FONT_OSS_PREFIX='test/fonts/')
class FontTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='font-admin',is_staff=True,is_superuser=True)
        self.client=APIClient();self.client.force_authenticate(self.user)
        self.family=FontFamily.objects.create(title='测试文楷')
        self.draft=FontDraft.objects.create(family=self.family,content=services.normalize({'title':'测试文楷'}))
    def asset(self,kind):
        return FontAsset.objects.create(family=self.family,kind=kind,object_key=f'test/fonts/{kind}',sha256='a'*64,byte_size=10,mime='font/ttf' if kind=='font' else 'image/png',metadata={'faces':[{'postscript_name':'Test-Regular'}]})
    def ready(self):
        font=self.asset('font');cover=self.asset('cover');preview=self.asset('preview');license=self.asset('license')
        self.draft.content=services.normalize(dict(title='测试文楷',faces=[dict(id='regular',asset_id=str(font.pk),postscript_name='Test-Regular',label='Regular')],default_face='regular',cover=str(cover.pk),previews=[str(preview.pk)],license_asset=str(license.pk),license_approved=True,license_scopes=['app','distribution'],languages=['简体中文']))
        self.draft.save()
        offer=ContentOffer.objects.create(target_kind='font',target_id=self.family.pk,title=self.family.title,state='active')
        policy=ContentPolicyRevision.objects.create(offer=offer,revision=1,access_mode='free')
        offer.current_policy_revision=policy;offer.save()
        return offer
    def test_publish_fails_closed_then_idempotent(self):
        with self.assertRaises(Exception): services.publish(self.family.pk,1,0,'first',self.user)
        self.assertEqual(FontRelease.objects.count(),0)
        self.ready()
        a=services.publish(self.family.pk,1,0,'first',self.user)
        b=services.publish(self.family.pk,1,0,'first',self.user)
        self.assertEqual(a.pk,b.pk)
        with self.assertRaises(Exception):services.publish(self.family.pk,1,0,'second',self.user)
        self.assertEqual(FontRelease.objects.count(),1)
    def test_stale_draft_returns_conflict(self):
        r=self.client.patch(f'/api/v1/fonts/manage/families/{self.family.pk}/draft/',{'expected_revision':0,'content':{'title':'bad'}},format='json')
        self.assertEqual(r.status_code,409);self.draft.refresh_from_db();self.assertEqual(self.draft.content['title'],'测试文楷')
    @patch('font_library.storage.sign',return_value='https://example.oss.aliyuncs.com/asset')
    def test_claim_preserves_access_after_takedown_and_policy_change(self,sign):
        offer=self.ready();services.publish(self.family.pk,1,0,'first',self.user)
        r=self.client.post(f'/api/v1/fonts/families/{self.family.pk}/claim/',{},format='json');self.assertEqual(r.status_code,200)
        self.family.refresh_from_db();self.family.active=False;self.family.save()
        body=dict(font_id=str(self.family.pk),version=1,face_id='regular')
        self.assertEqual(self.client.post('/api/v1/fonts/download-plans/',body,format='json').status_code,200)
        other=get_user_model().objects.create_user(username='other');self.client.force_authenticate(other)
        self.assertEqual(self.client.post('/api/v1/fonts/download-plans/',body,format='json').status_code,403)
        self.assertEqual(self.client.post('/api/v1/fonts/download-plans/',{**body,'purpose':'restore','document_id':str(uuid.uuid4())},format='json').status_code,403)
    def test_non_staff_cannot_manage(self):
        user=get_user_model().objects.create_user(username='regular');self.client.force_authenticate(user)
        self.assertEqual(self.client.get('/api/v1/fonts/manage/families/').status_code,403)
    def test_upload_does_not_accept_file_body(self):
        r=self.client.post('/api/v1/fonts/manage/uploads/',b'x'*300000,content_type='application/octet-stream')
        self.assertIn(r.status_code,[413,415])
    @patch('font_library.storage.bucket')
    def test_complete_only_head_copy_never_reads_body(self,bucket):
        etag='01'*16;head=Mock(content_length=10,content_type='font/ttf',etag=etag)
        bucket.return_value.head_object.return_value=head
        job=FontUpload.objects.create(family=self.family,actor=self.user,kind='font',name='test.ttf',object_key='test/fonts/uploads/a',byte_size=10,mime='font/ttf',md5=base64.b64encode(bytes.fromhex(etag)).decode(),declared_sha256='a'*64,expires_at=timezone.now()+timedelta(hours=1))
        r=self.client.post(f'/api/v1/fonts/manage/uploads/{job.pk}/complete/',{},format='json')
        self.assertEqual(r.status_code,200);self.assertEqual(r.data['state'],'queued')
        bucket.return_value.get_object.assert_not_called();bucket.return_value.put_object.assert_not_called();bucket.return_value.copy_object.assert_called_once()
    @patch('font_library.storage.sign',return_value='https://example.test/file')
    def test_processor_requires_secret_and_valid_lease(self,sign):
        job=FontUpload.objects.create(family=self.family,actor=self.user,kind='font',name='test.ttf',object_key='test/fonts/temp',candidate_key='test/fonts/frozen',byte_size=10,mime='font/ttf',md5='a',declared_sha256='a'*64,state='queued',expires_at=timezone.now())
        client=APIClient();path='/api/v1/fonts/processor/'
        self.assertEqual(client.post(path,{'action':'claim'},format='json').status_code,403)
        client.credentials(HTTP_AUTHORIZATION='Bearer test-processor')
        r=client.post(path,{'action':'claim'},format='json');self.assertEqual(r.status_code,200)
        self.assertEqual(client.post(path,{'action':'complete','id':str(job.pk),'token':str(uuid.uuid4())},format='json').status_code,409)
