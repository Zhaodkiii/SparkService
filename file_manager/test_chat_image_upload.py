"""聊天图片上传会话与登记接口测试（CHAT-WEB-029）。"""

from __future__ import annotations

import hashlib
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from file_manager.models import ManagedFile
from file_manager.services.oss_object_service import OssObjectMeta, OssUploadError

SESSION_URL = "/api/v1/oss/chat-images/upload-sessions/"
COMPLETE_URL_TEMPLATE = "/api/v1/oss/chat-images/upload-sessions/{session_id}/complete/"
SIGN_PATCH_TARGET = "file_manager.chat_image_views._sign_upload_url"
META_PATCH_TARGET = "file_manager.chat_image_views.object_meta"
GET_BYTES_PATCH_TARGET = "file_manager.chat_image_views.get_bytes"

FAKE_SIGNED_URL = "https://oss-cn-test.aliyuncs.com/test-bucket/signed-put-url"


def make_image_bytes(fmt="WEBP", size=(64, 64), color=(10, 120, 200)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def fake_meta(object_key, content_length):
    return OssObjectMeta(object_key=object_key, content_length=content_length, content_type="image/webp", etag="etag")


@override_settings(
    ALIYUN_OSS_ENDPOINT="https://oss-cn-test.aliyuncs.com",
    ALIYUN_OSS_BUCKET="test-bucket",
)
class ChatImageUploadSessionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="chat-image-user")
        self.client.force_authenticate(self.user)

    def _create_session(self, **overrides):
        payload = {
            "purpose": "chat_image",
            "mime_type": "image/webp",
            "file_size": 1024,
            "client_upload_id": "upload-0001",
            **overrides,
        }
        return self.client.post(SESSION_URL, payload, format="json")

    def test_create_session_success(self):
        with mock.patch(SIGN_PATCH_TARGET, return_value=FAKE_SIGNED_URL):
            response = self._create_session()
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data["data"]
        self.assertTrue(data["upload_session_id"])
        self.assertTrue(data["object_key"].startswith("zhaodkdream/spark_service/chat/image/"))
        self.assertTrue(data["object_key"].endswith(".webp"))
        self.assertEqual(data["upload_url"], FAKE_SIGNED_URL)
        self.assertEqual(data["upload_url_expires_in"], 900)
        self.assertEqual(data["method"], "PUT")
        self.assertEqual(data["required_headers"], {"Content-Type": "image/webp"})
        self.assertEqual(data["max_file_size"], 10 * 1024 * 1024)
        self.assertIn("test-bucket", data["display_url"])
        # 不下发任何长期凭证字段
        for leaked in ("access_key_id", "access_key_secret", "security_token"):
            self.assertNotIn(leaked, data)

    def test_create_session_idempotent_replay(self):
        with mock.patch(SIGN_PATCH_TARGET, return_value=FAKE_SIGNED_URL):
            first = self._create_session()
            second = self._create_session()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["msg"], "replayed")
        self.assertEqual(first.data["data"]["upload_session_id"], second.data["data"]["upload_session_id"])
        self.assertEqual(first.data["data"]["object_key"], second.data["data"]["object_key"])

    def test_create_session_invalid_mime_rejected(self):
        response = self._create_session(mime_type="image/svg+xml")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "chat_image_format_invalid")
        self.assertEqual(response.data["code"], 40100)

    def test_create_session_oversize_rejected(self):
        response = self._create_session(file_size=10 * 1024 * 1024 + 1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "chat_image_format_invalid")

    def test_create_session_missing_client_upload_id_rejected(self):
        response = self._create_session(client_upload_id="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "chat_image_format_invalid")

    def test_create_session_wrong_purpose_rejected(self):
        response = self._create_session(purpose="avatar")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "chat_image_format_invalid")


@override_settings(
    ALIYUN_OSS_ENDPOINT="https://oss-cn-test.aliyuncs.com",
    ALIYUN_OSS_BUCKET="test-bucket",
)
class ChatImageUploadCompleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="chat-image-complete-user")
        self.client.force_authenticate(self.user)
        self.raw = make_image_bytes(fmt="WEBP")

    def _create_session(self, **overrides):
        payload = {
            "purpose": "chat_image",
            "mime_type": "image/webp",
            "file_size": len(self.raw),
            "client_upload_id": "upload-complete-1",
            **overrides,
        }
        with mock.patch(SIGN_PATCH_TARGET, return_value=FAKE_SIGNED_URL):
            response = self.client.post(SESSION_URL, payload, format="json")
        assert response.status_code == 201, response.data
        return response.data["data"]

    def _complete(self, session, **overrides):
        payload = {
            "client_upload_id": "upload-complete-1",
            "object_key": session["object_key"],
            "mime_type": "image/webp",
            "file_size": len(self.raw),
            **overrides,
        }
        url = COMPLETE_URL_TEMPLATE.format(session_id=session["upload_session_id"])
        return self.client.post(url, payload, format="json")

    def test_complete_success(self):
        session = self._create_session()
        raw = self.raw
        with mock.patch(META_PATCH_TARGET, side_effect=lambda *, object_key: fake_meta(object_key, len(raw))), \
            mock.patch(GET_BYTES_PATCH_TARGET, side_effect=lambda *, object_key, max_bytes: raw):
            response = self._complete(session, file_md5=hashlib.md5(raw).hexdigest())
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data["data"]
        self.assertEqual(data["status"], "ready")
        self.assertTrue(data["file_id"])
        self.assertTrue(data["file_uuid"])
        self.assertTrue(data["version"])
        self.assertIn("test-bucket", data["display_url"])

        record = ManagedFile.objects.get(pk=data["file_id"])
        self.assertEqual(record.user_id, self.user.id)
        self.assertEqual(record.mime_type, "image/webp")
        self.assertEqual(record.file_size, len(raw))
        self.assertEqual(record.file_md5, hashlib.md5(raw).hexdigest())
        self.assertTrue(record.is_public)
        self.assertEqual(record.object_key, session["object_key"])
        self.assertEqual(record.storage_type, "oss")
        self.assertEqual(str(record.file_uuid), data["file_uuid"])

    def test_complete_replay_returns_same_file_id(self):
        session = self._create_session()
        raw = self.raw
        with mock.patch(META_PATCH_TARGET, side_effect=lambda *, object_key: fake_meta(object_key, len(raw))), \
            mock.patch(GET_BYTES_PATCH_TARGET, side_effect=lambda *, object_key, max_bytes: raw):
            first = self._complete(session)
            second = self._complete(session)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["msg"], "replayed")
        self.assertEqual(first.data["data"]["file_id"], second.data["data"]["file_id"])
        self.assertEqual(ManagedFile.objects.count(), 1)

    def test_complete_missing_object_rejected(self):
        session = self._create_session()
        with mock.patch(META_PATCH_TARGET, side_effect=OssUploadError("oss_object_not_found")):
            response = self._complete(session)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "chat_image_registration_failed")
        self.assertEqual(response.data["code"], 40202)
        self.assertEqual(ManagedFile.objects.count(), 0)

    def test_complete_md5_mismatch_rejected(self):
        session = self._create_session()
        raw = self.raw
        with mock.patch(META_PATCH_TARGET, side_effect=lambda *, object_key: fake_meta(object_key, len(raw))), \
            mock.patch(GET_BYTES_PATCH_TARGET, side_effect=lambda *, object_key, max_bytes: raw):
            response = self._complete(session, file_md5="0" * 32)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "chat_image_registration_failed")
        self.assertEqual(ManagedFile.objects.count(), 0)

    def test_complete_non_image_bytes_rejected(self):
        junk = b"not-an-image!!!"
        session = self._create_session(file_size=len(junk))
        with mock.patch(META_PATCH_TARGET, side_effect=lambda *, object_key: fake_meta(object_key, len(junk))), \
            mock.patch(GET_BYTES_PATCH_TARGET, side_effect=lambda *, object_key, max_bytes: junk):
            response = self._complete(session)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "chat_image_format_invalid")
        self.assertEqual(response.data["code"], 40100)
        self.assertEqual(ManagedFile.objects.count(), 0)

    def test_complete_mime_mismatch_rejected(self):
        # 声明 webp，实际字节是 PNG
        session = self._create_session()
        raw = make_image_bytes(fmt="PNG")
        session["file_size"] = len(raw)
        with mock.patch(META_PATCH_TARGET, side_effect=lambda *, object_key: fake_meta(object_key, len(self.raw))), \
            mock.patch(GET_BYTES_PATCH_TARGET, side_effect=lambda *, object_key, max_bytes: raw):
            response = self._complete(session, file_size=len(self.raw))
        self.assertEqual(response.status_code, 400)
        self.assertIn(response.data["msg"], {"chat_image_format_invalid", "chat_image_registration_failed"})
        self.assertEqual(ManagedFile.objects.count(), 0)

    def test_complete_object_key_mismatch_rejected(self):
        session = self._create_session()
        response = self._complete(session, object_key="zhaodkdream/spark_service/chat/image/others.webp")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "chat_image_registration_failed")

    def test_complete_unknown_session_rejected(self):
        url = COMPLETE_URL_TEMPLATE.format(session_id="0" * 32)
        response = self.client.post(
            url,
            {
                "client_upload_id": "upload-complete-1",
                "object_key": "zhaodkdream/spark_service/chat/image/x.webp",
                "mime_type": "image/webp",
                "file_size": 10,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["msg"], "chat_image_not_found")
        self.assertEqual(response.data["code"], 40492)

    def test_complete_reuses_existing_managed_file(self):
        session = self._create_session()
        existing = ManagedFile.objects.create(
            user=self.user,
            original_name="existing.webp",
            file_ext="webp",
            mime_type="image/webp",
            file_size=len(self.raw),
            is_public=True,
            object_key=session["object_key"],
            storage_type="oss",
        )
        # 已登记同 object_key：不再访问 OSS，直接复用同一 file_id
        response = self._complete(session)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["file_id"], existing.id)
        self.assertEqual(ManagedFile.objects.count(), 1)
