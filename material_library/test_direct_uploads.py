import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from .models import MaterialUpload, ResourceBlob


@override_settings(MIDDLEWARE=[],MATERIAL_UPLOADS_ENABLED=True,ALIYUN_ACCESS_KEY_ID='test',
    ALIYUN_ACCESS_KEY_SECRET='test',ALIYUN_OSS_ENDPOINT='https://oss-cn-hangzhou.aliyuncs.com',ALIYUN_OSS_BUCKET='test')
class DirectUploadTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='uploader',is_superuser=True,is_staff=True)
        self.client=APIClient();self.client.force_authenticate(self.user)
        self.oss=MagicMock();self.oss.sign_url.return_value='https://test.oss-cn-hangzhou.aliyuncs.com/upload?signed'
        self.patch=patch('material_library.direct_uploads.bucket',return_value=self.oss);self.patch.start();self.addCleanup(self.patch.stop)
        self.sign=patch('material_library.catalog_v2.sign',return_value='https://test.oss-cn-hangzhou.aliyuncs.com/image');self.sign.start();self.addCleanup(self.sign.stop)
        self.original=dict(sha256='a'*64,md5=base64.b64encode(bytes.fromhex('c'*32)).decode(),byte_size=2000,width=512,height=512,mime='image/png',has_visible_pixels=True,has_transparency=True)
        self.thumb=dict(sha256='b'*64,md5=base64.b64encode(bytes.fromhex('d'*32)).decode(),byte_size=1000,width=256,height=256,mime='image/png')
        self.body=dict(name='flower.png',purpose='sticker',original=self.original,thumbnail=self.thumb)
        self.objects={}
        self.oss.head_object.side_effect=lambda key:self.objects[key]
        self.oss.copy_object.side_effect=lambda bucket,source,target,headers:self.objects.__setitem__(target,self.objects[source])

    def start_upload(self):
        response=self.client.post('/api/v1/materials/manage/uploads/',self.body,format='json')
        self.assertEqual(response.status_code,201,response.data)
        upload=MaterialUpload.objects.get(pk=response.data['id'])
        for key,info in [(upload.object_key,self.original),(upload.object_key+'/thumbnail',self.thumb)]:
            self.objects[key]=SimpleNamespace(content_length=info['byte_size'],etag=base64.b64decode(info['md5']).hex(),content_type=info['mime'])
        return upload,response

    def complete(self,upload):
        return self.client.post(f'/api/v1/materials/manage/uploads/{upload.pk}/complete/',{},format='json')

    def test_direct_upload_returns_two_signed_puts_without_sts(self):
        upload,response=self.start_upload()
        self.assertEqual(set(response.data['uploads']),{'original','thumbnail'})
        self.assertNotIn('credentials',response.data)
        for call in self.oss.sign_url.call_args_list:
            self.assertEqual(call.args[0],'PUT')
            self.assertIn('Content-MD5',call.kwargs['headers'])
            self.assertTrue(call.args[1].startswith('traveldiary/presets/material-uploads/'))
        self.assertEqual(upload.upload_metadata['protocol'],2)

    def test_confirmation_is_idempotent_and_never_transfers_bodies(self):
        upload,_=self.start_upload();response=self.complete(upload)
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['state'],'verified')
        self.assertEqual(response.data['confirmation'],'oss-metadata')
        self.assertEqual(ResourceBlob.objects.count(),2)
        self.assertEqual(self.oss.copy_object.call_count,2)
        for call in self.oss.copy_object.call_args_list:
            self.assertTrue(call.args[2].startswith('traveldiary/presets/blobs/'))
            self.assertIn('x-oss-copy-source-if-match',call.kwargs['headers'])
        self.assertEqual(self.complete(upload).status_code,200)
        self.assertEqual(self.oss.copy_object.call_count,2)
        self.oss.get_object.assert_not_called();self.oss.put_object.assert_not_called()

    def test_wrong_size_or_checksum_is_not_registered(self):
        for field,value in [('content_length',1),('etag','0'*32),('content_type','text/html')]:
            with self.subTest(field=field):
                upload,_=self.start_upload();setattr(self.objects[upload.object_key],field,value)
                self.assertEqual(self.complete(upload).status_code,400)
                self.assertFalse(ResourceBlob.objects.exists())
                upload.refresh_from_db();self.assertNotEqual(upload.state,'verified')

    def test_duplicate_files_reuse_resources_without_new_formal_copies(self):
        first,_=self.start_upload();result=self.complete(first)
        second,_=self.start_upload();again=self.complete(second)
        self.assertEqual(again.status_code,200,again.data)
        self.assertEqual(result.data['resource']['resource_id'],again.data['resource']['resource_id'])
        self.assertEqual(ResourceBlob.objects.count(),2)
        self.assertEqual(self.oss.copy_object.call_count,2)

    def test_partial_confirmation_can_retry_after_oss_failure(self):
        upload,_=self.start_upload()
        original_copy=self.oss.copy_object.side_effect
        def fail_thumb(bucket,source,target,headers):
            if target.endswith('/thumbnail'): raise RuntimeError('secret signed URL must not escape')
            return original_copy(bucket,source,target,headers)
        self.oss.copy_object.side_effect=fail_thumb
        response=self.complete(upload)
        self.assertEqual(response.status_code,503)
        self.assertNotIn('secret',str(response.data));self.assertFalse(ResourceBlob.objects.exists())
        self.oss.copy_object.side_effect=original_copy
        self.assertEqual(self.complete(upload).status_code,200)

    def test_other_admin_cannot_confirm_or_query_upload(self):
        upload,_=self.start_upload()
        other=get_user_model().objects.create_user(username='other',is_superuser=True,is_staff=True)
        self.client.force_authenticate(other)
        self.assertEqual(self.complete(upload).status_code,404)
        self.assertEqual(self.client.get(f'/api/v1/materials/manage/uploads/{upload.pk}/').status_code,404)

    def test_browser_metadata_limits_and_thumbnail_ratio_are_enforced(self):
        for field,value in [('width',9000),('has_transparency',False),('has_visible_pixels',False),('mime','image/svg+xml')]:
            response=self.client.post('/api/v1/materials/manage/uploads/',{**self.body,'original':{**self.original,field:value}},format='json')
            self.assertEqual(response.status_code,400,response.data)
        response=self.client.post('/api/v1/materials/manage/uploads/',{**self.body,'thumbnail':{**self.thumb,'width':200}},format='json')
        self.assertEqual(response.status_code,400)
        self.oss.sign_url.assert_not_called()

    @override_settings(MATERIAL_UPLOADS_ENABLED=False)
    def test_optional_upload_switch_is_independent_of_workers(self):
        response=self.client.get('/api/v1/materials/manage/options/')
        self.assertFalse(response.data['uploads_enabled'])
        self.assertNotIn('独立',response.data['upload_unavailable_reason'])
        self.assertEqual(self.client.post('/api/v1/materials/manage/uploads/',self.body,format='json').status_code,400)
