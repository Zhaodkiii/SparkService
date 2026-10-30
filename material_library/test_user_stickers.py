import uuid
from types import SimpleNamespace
from unittest.mock import patch, Mock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import UserSticker


@patch('material_library.user_stickers.bucket')
class UserStickerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='sticker-owner')
        self.other = get_user_model().objects.create_user(username='sticker-other')
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.base = '/api/v1/materials/personal/'

    def plan(self, bucket):
        bucket.return_value.sign_url.return_value = 'https://bucket.oss-cn-beijing.aliyuncs.com/test'
        return self.client.post(self.base+'uploads/', {'uuid':str(uuid.uuid4()), 'byteSize':123}, format='json')

    def test_upload_is_scoped_and_registration_is_idempotent(self, bucket):
        plan = self.plan(bucket)
        self.assertEqual(plan.status_code, 200)
        self.assertIn(f'user-content/stickers/{self.user.pk}/', plan.data['imageObjectKey'])
        self.assertEqual(plan.data['headers']['x-oss-forbid-overwrite'], 'true')
        self.assertEqual(UserSticker.objects.count(), 0)
        bucket.return_value.head_object.return_value = SimpleNamespace(content_length=123, content_type='image/png')
        body = {k:plan.data[k] for k in ['imageObjectKey', 'token']}
        first = self.client.post(self.base+'stickers/',body,format='json')
        self.assertEqual(first.status_code,201)
        second = self.client.post(self.base+'stickers/',body,format='json')
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(UserSticker.objects.count(),1)

    def test_cross_account_and_path_tampering_rejected(self,bucket):
        plan = self.plan(bucket).data
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(self.base+'stickers/',plan,format='json').status_code,400)
        self.client.force_authenticate(self.user)
        plan['imageObjectKey'] += 'changed'
        self.assertEqual(self.client.post(self.base+'stickers/',plan,format='json').status_code,400)
        bucket.return_value.head_object.assert_not_called()

    def test_delete_is_owner_scoped_and_retains_oss(self,bucket):
        row = UserSticker.objects.create(owner=self.user,image_object_key='test.png')
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(self.base+f'stickers/{row.pk}/').status_code,404)
        self.assertEqual(self.client.get(self.base+'stickers/').data['items'],[])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(self.base+f'stickers/{row.pk}/').status_code,204)
        bucket.return_value.delete_object.assert_not_called()

    def test_head_mismatch_does_not_register(self,bucket):
        plan=self.plan(bucket).data
        bucket.return_value.head_object.return_value=SimpleNamespace(content_length=999,content_type='image/png')
        self.assertEqual(self.client.post(self.base+'stickers/',plan,format='json').status_code,400)
        self.assertEqual(UserSticker.objects.count(),0)

    def test_client_normalized_path_and_snake_case_body(self, bucket):
        bucket.return_value.sign_url.return_value = 'https://bucket.oss-cn-beijing.aliyuncs.com/test'
        plan = self.client.post(self.base+'uploads', {'uuid': str(uuid.uuid4()), 'byte_size': '123'}, format='json')
        self.assertEqual(plan.status_code, 200)
        bucket.return_value.head_object.return_value = SimpleNamespace(content_length=123, content_type='image/png')
        result = self.client.post(self.base+'stickers', {'image_object_key': plan.data['imageObjectKey'], 'token': plan.data['token']}, format='json')
        self.assertEqual(result.status_code, 201)
        self.assertEqual(self.client.get(self.base+'stickers').status_code, 200)
        self.assertEqual(self.client.delete(self.base+f"stickers/{result.data['id']}").status_code, 204)
