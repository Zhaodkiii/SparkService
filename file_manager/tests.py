from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

User = get_user_model()

_MOCK_STS = {
    "access_key_id": "STS.NKfake",
    "access_key_secret": "fake-secret",
    "security_token": "fake-token",
    "expiration": 1_700_000_000,
    "bucket_name": "test-bucket",
    "region": "cn-hangzhou",
    "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
}


class OssSTSAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="oss_tester",
            email="oss@example.com",
            password="test123456",
        )
        self.client.force_authenticate(self.user)

    @patch("file_manager.oss_sts_views.get_sts_credentials", return_value=_MOCK_STS.copy())
    def test_oss_sts_wrapped_success(self, _mock):
        r = self.client.get("/api/v1/oss/sts/credentials/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        body = r.json()
        self.assertEqual(body["code"], 0)
        self.assertIn("data", body)
        data = body["data"]
        self.assertEqual(data["access_key_id"], _MOCK_STS["access_key_id"])
        self.assertEqual(data["expiration"], _MOCK_STS["expiration"])
        self.assertEqual(data["bucket_name"], _MOCK_STS["bucket_name"])

    @patch("file_manager.oss_sts_views.get_sts_credentials", return_value=_MOCK_STS.copy())
    def test_ocr_sts_wrapped_success(self, _mock):
        r = self.client.get("/api/v1/oss/ocr/sts/credentials/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        body = r.json()
        self.assertEqual(body["code"], 0)
        self.assertEqual(body["data"]["security_token"], "fake-token")

    @patch("file_manager.oss_sts_views.get_sts_credentials", side_effect=ValueError("missing ak"))
    def test_sts_config_error(self, _mock):
        r = self.client.get("/api/v1/oss/sts/credentials/")
        self.assertEqual(r.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(r.json()["code"], 5001)

    def test_sts_requires_auth(self):
        bare = APIClient()
        r = bare.get("/api/v1/oss/sts/credentials/")
        self.assertIn(r.status_code, (401, 403))
