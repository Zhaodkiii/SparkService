"""公开图片上传接口与头像图片处理测试（BACKOFFICE-HOSPITAL-AGENT-000002）。"""

from __future__ import annotations

from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from file_manager.constants import (
    AGENT_AVATAR_KEY_TEMPLATE,
    BUSINESS_TYPE_CLINICAL_AGENT_AVATAR,
)
from file_manager.models import ManagedFile, ManagedFileBusinessRelation
from file_manager.services.image_processing import AvatarProcessingError, build_agent_avatar
from file_manager.services.oss_object_service import OssUploadError, PutObjectResult
from hospital_care.models import Hospital
from hospital_care.tests.factories import make_hospital, make_user


def make_image_bytes(fmt="PNG", size=(800, 600), color=(200, 30, 30), *, frames=None) -> bytes:
    buffer = BytesIO()
    if frames:
        images = [Image.new("RGB", size, color)]
        for extra in range(frames - 1):
            images.append(Image.new("RGB", size, (30, 30, 200 + extra)))
        images[0].save(buffer, format=fmt, save_all=True, append_images=images[1:], duration=100, loop=0)
    else:
        Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def make_two_tone_image_bytes(size=(1000, 500)) -> bytes:
    """左红右蓝图片，用于验证裁剪区域生效。"""
    image = Image.new("RGB", size, (220, 20, 20))
    for x in range(size[0] // 2, size[0]):
        for y in range(size[1]):
            image.putpixel((x, y), (20, 20, 220))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def fake_put_result(object_key):
    return PutObjectResult(object_key=object_key, etag="etag", request_id="req-1", version_id="", crc64="0")


class ImageProcessingTests(TestCase):
    def test_jpg_png_webp_all_convert_to_1024_webp(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            raw = make_image_bytes(fmt=fmt, size=(900, 700))
            result = build_agent_avatar(raw, crop_x=0.0, crop_y=0.0, crop_size=1.0)
            with Image.open(BytesIO(result.content)) as output:
                self.assertEqual(output.format, "WEBP")
                self.assertEqual(output.size, (1024, 1024))
                self.assertFalse(output.getexif())
            self.assertEqual(result.width, 1024)
            self.assertTrue(result.file_md5)

    def test_crop_region_applied(self):
        raw = make_two_tone_image_bytes(size=(1000, 500))
        # 左半部分裁剪（红）与右半部分裁剪（蓝）应产生不同输出
        left = build_agent_avatar(raw, crop_x=0.0, crop_y=0.0, crop_size=0.5)
        right = build_agent_avatar(raw, crop_x=0.5, crop_y=0.0, crop_size=0.5)
        self.assertNotEqual(left.file_md5, right.file_md5)

    def test_oversize_bytes_rejected(self):
        with self.assertRaises(AvatarProcessingError) as ctx:
            build_agent_avatar(b"x" * (5 * 1024 * 1024 + 1), crop_x=0.0, crop_y=0.0, crop_size=1.0)
        self.assertEqual(str(ctx.exception), "AVATAR_FILE_TOO_LARGE")

    def test_long_edge_over_2048_rejected(self):
        raw = make_image_bytes(size=(2100, 100))
        with self.assertRaises(AvatarProcessingError) as ctx:
            build_agent_avatar(raw, crop_x=0.0, crop_y=0.0, crop_size=1.0)
        self.assertEqual(str(ctx.exception), "AVATAR_DIMENSION_EXCEEDED")

    def test_corrupt_image_rejected(self):
        with self.assertRaises(AvatarProcessingError) as ctx:
            build_agent_avatar(b"not-an-image-at-all", crop_x=0.0, crop_y=0.0, crop_size=1.0)
        self.assertEqual(str(ctx.exception), "AVATAR_FORMAT_INVALID")

    def test_non_image_format_rejected(self):
        buffer = BytesIO()
        buffer.write(b"%PDF-1.4 fake pdf content")
        with self.assertRaises(AvatarProcessingError) as ctx:
            build_agent_avatar(buffer.getvalue(), crop_x=0.0, crop_y=0.0, crop_size=1.0)
        self.assertEqual(str(ctx.exception), "AVATAR_FORMAT_INVALID")

    def test_gif_format_rejected(self):
        raw = make_image_bytes(fmt="GIF", size=(100, 100))
        with self.assertRaises(AvatarProcessingError) as ctx:
            build_agent_avatar(raw, crop_x=0.0, crop_y=0.0, crop_size=1.0)
        self.assertEqual(str(ctx.exception), "AVATAR_FORMAT_INVALID")

    def test_animated_webp_rejected(self):
        raw = make_image_bytes(fmt="WEBP", size=(100, 100), frames=2)
        with self.assertRaises(AvatarProcessingError) as ctx:
            build_agent_avatar(raw, crop_x=0.0, crop_y=0.0, crop_size=1.0)
        self.assertEqual(str(ctx.exception), "AVATAR_ANIMATED_NOT_ALLOWED")

    def test_invalid_crop_params_rejected(self):
        raw = make_image_bytes(size=(500, 500))
        for params in (
            {"crop_x": -0.1, "crop_y": 0.0, "crop_size": 0.5},
            {"crop_x": 0.0, "crop_y": 0.0, "crop_size": 0.0},
            {"crop_x": 0.6, "crop_y": 0.0, "crop_size": 0.5},
            {"crop_x": 0.0, "crop_y": 0.6, "crop_size": 0.5},
            {"crop_x": float("nan"), "crop_y": 0.0, "crop_size": 0.5},
        ):
            with self.assertRaises(AvatarProcessingError) as ctx:
                build_agent_avatar(raw, **params)
            self.assertEqual(str(ctx.exception), "AVATAR_CROP_INVALID")

    def test_exif_orientation_transposed_before_crop(self):
        buffer = BytesIO()
        image = Image.new("RGB", (1200, 600), (10, 200, 10))
        exif = Image.Exif()
        exif[274] = 6  # 旋转 90°
        image.save(buffer, format="JPEG", exif=exif)
        result = build_agent_avatar(buffer.getvalue(), crop_x=0.0, crop_y=0.0, crop_size=1.0)
        with Image.open(BytesIO(result.content)) as output:
            self.assertEqual(output.size, (1024, 1024))


@override_settings(
    ALIYUN_OSS_ENDPOINT="https://oss-cn-test.aliyuncs.com",
    ALIYUN_OSS_BUCKET="test-bucket",
)
class PublicImageUploadApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.service_user = make_user("hospital-service")
        self.hospital = make_hospital(code="UP-H", knowledge_service_user=self.service_user)
        self.url = "/api/v1/public/uploads/images/"

    def _post(self, file_bytes, name="avatar.png", **fields):
        payload = {
            "purpose": "clinical_agent_avatar",
            "hospital_id": str(self.hospital.id),
            "crop_x": "0.0",
            "crop_y": "0.0",
            "crop_size": "1.0",
            **fields,
        }
        upload = SimpleUploadedFile(name, file_bytes, content_type="image/png")
        return self.client.post(self.url, {**payload, "file": upload}, format="multipart")

    @mock.patch("file_manager.public_views.put_bytes", side_effect=lambda *, object_key, content, content_type: fake_put_result(object_key))
    def test_upload_success_without_login(self, put_mock):
        response = self._post(make_image_bytes(size=(800, 800)))
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data["data"]
        self.assertEqual(data["mime_type"], "image/webp")
        self.assertEqual(data["width"], 1024)
        self.assertEqual(data["height"], 1024)
        self.assertEqual(data["binding_state"], "unbound")
        self.assertIn("v=", data["avatar_url"])

        record = ManagedFile.objects.get(pk=data["file_id"])
        self.assertEqual(str(record.file_uuid), data["file_uuid"])
        self.assertEqual(record.user_id, self.service_user.id)
        self.assertEqual(record.mime_type, "image/webp")
        self.assertTrue(
            record.object_key.startswith(f"zhaodkdream/spark_service/hospital/avatar/{self.hospital.id}/")
        )
        self.assertTrue(record.object_key.endswith(".webp"))
        self.assertNotIn("avatar.png", record.object_key)
        relation = ManagedFileBusinessRelation.objects.get(
            file=record, business_type=BUSINESS_TYPE_CLINICAL_AGENT_AVATAR
        )
        self.assertEqual(relation.business_id, "")
        # OSS 上传参数校验
        _, kwargs = put_mock.call_args
        self.assertEqual(kwargs["content_type"], "image/webp")

    @mock.patch("file_manager.public_views.put_bytes", side_effect=lambda *, object_key, content, content_type: fake_put_result(object_key))
    def test_upload_oversize_rejected(self, _):
        response = self._post(b"x" * (5 * 1024 * 1024 + 1))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data["msg"], "AVATAR_FILE_TOO_LARGE")

    @mock.patch("file_manager.public_views.put_bytes")
    def test_upload_fake_image_rejected(self, put_mock):
        response = self._post(b"this is not an image", name="fake.jpg")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "AVATAR_FORMAT_INVALID")
        put_mock.assert_not_called()

    @mock.patch("file_manager.public_views.put_bytes")
    def test_upload_svg_rejected(self, put_mock):
        response = self._post(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', name="x.svg")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "AVATAR_FORMAT_INVALID")
        put_mock.assert_not_called()

    @mock.patch("file_manager.public_views.put_bytes")
    def test_upload_invalid_crop_rejected(self, put_mock):
        response = self._post(make_image_bytes(size=(500, 500)), crop_x="0.8", crop_size="0.5")
        self.assertEqual(response.status_code, 400)
        put_mock.assert_not_called()

    @mock.patch("file_manager.public_views.put_bytes", side_effect=lambda *, object_key, content, content_type: fake_put_result(object_key))
    def test_doctor_avatar_purpose_uses_doctor_key_and_relation(self, _):
        response = self._post(make_image_bytes(size=(400, 400)), purpose="doctor_avatar")
        self.assertEqual(response.status_code, 201, response.data)
        record = ManagedFile.objects.get(pk=response.data["data"]["file_id"])
        self.assertTrue(
            record.object_key.startswith(f"zhaodkdream/spark_service/hospital/doctor/avatar/{self.hospital.id}/")
        )
        relation = ManagedFileBusinessRelation.objects.get(file=record)
        self.assertEqual(relation.business_type, "doctor_avatar_upload")
        self.assertEqual(relation.business_id, "")

    @mock.patch("file_manager.public_views.put_bytes")
    def test_wrong_purpose_rejected(self, put_mock):
        response = self._post(make_image_bytes(size=(100, 100)), purpose="anything_else")
        self.assertEqual(response.status_code, 400)
        put_mock.assert_not_called()

    @mock.patch("file_manager.public_views.put_bytes")
    def test_unknown_hospital_rejected(self, put_mock):
        import uuid as uuid_module

        response = self._post(make_image_bytes(size=(100, 100)), hospital_id=str(uuid_module.uuid4()))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["msg"], "HOSPITAL_NOT_FOUND")
        put_mock.assert_not_called()

    @mock.patch("file_manager.public_views.put_bytes")
    def test_hospital_without_service_user_rejected(self, put_mock):
        hospital = Hospital.objects.create(
            code="UP-H2", name="无服务账号医院", address="测试", province_code="340000", city_code="341100",
            status="active",
        )
        response = self._post(make_image_bytes(size=(100, 100)), hospital_id=str(hospital.id))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "HOSPITAL_SERVICE_USER_REQUIRED")
        put_mock.assert_not_called()

    @mock.patch(
        "file_manager.public_views.put_bytes",
        side_effect=OssUploadError("boom"),
    )
    def test_oss_failure_returns_503(self, _):
        response = self._post(make_image_bytes(size=(100, 100)))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["msg"], "AVATAR_UPLOAD_FAILED")
        self.assertEqual(ManagedFile.objects.count(), 0)


@override_settings(
    ALIYUN_OSS_ENDPOINT="https://oss-cn-test.aliyuncs.com",
    ALIYUN_OSS_BUCKET="test-bucket",
)
class AvatarFileDeleteProtectionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = make_user("file-owner")
        self.client.force_authenticate(self.owner)

    def _make_file(self, *, with_relation=True):
        record = ManagedFile.objects.create(
            user=self.owner,
            original_name="avatar.webp",
            mime_type="image/webp",
            file_size=10,
            object_key="zhaodkdream/spark_service/hospital/avatar/x/1.webp",
        )
        if with_relation:
            ManagedFileBusinessRelation.objects.create(
                file=record,
                user=self.owner,
                business_type=BUSINESS_TYPE_CLINICAL_AGENT_AVATAR,
                business_id="",
            )
        return record

    def test_unbound_avatar_file_delete_rejected(self):
        record = self._make_file()
        response = self.client.delete(f"/api/v1/files/{record.id}/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "FILE_RETENTION_PROTECTED")
        record.refresh_from_db()
        self.assertFalse(record.is_deleted)

    def test_bound_avatar_file_delete_rejected(self):
        record = self._make_file()
        relation = record.business_relations.get()
        relation.business_id = "some-agent-id"
        relation.save(update_fields=["business_id"])
        response = self.client.delete(f"/api/v1/files/{record.id}/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "FILE_RETENTION_PROTECTED")

    def test_doctor_avatar_file_delete_rejected(self):
        record = self._make_file()
        relation = record.business_relations.get()
        relation.business_type = "doctor_avatar_upload"
        relation.save(update_fields=["business_type"])
        response = self.client.delete(f"/api/v1/files/{record.id}/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "FILE_RETENTION_PROTECTED")

    def test_normal_file_delete_allowed(self):
        record = self._make_file(with_relation=False)
        response = self.client.delete(f"/api/v1/files/{record.id}/")
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertTrue(record.is_deleted)
