"""CreateRun 图片附件校验与 client_message_id 幂等测试（CHAT-WEB-029）。"""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from chat_sync.ai_models import RunStatus
from chat_sync.ai_runtime.providers.types import ProviderRoute
from chat_sync.ai_services.run_service import RunService
from chat_sync.models import ChatMessage, ChatThread
from chat_sync.tests.run_factory import canonical_run_payload
from common.exceptions import APIError
from file_manager.models import ManagedFile

ROUTE_PATCH_TARGET = "chat_sync.ai_runtime.providers.factory.resolve_chat_route"


def make_route(*, supports_multimodal: bool) -> ProviderRoute:
    return ProviderRoute(
        provider="test-provider",
        model="test-model",
        endpoint="https://provider.example.com",
        api_key="test-key",
        supports_multimodal=supports_multimodal,
    )


def image_gallery_block(*, image_count: int, order_key: float = 1100) -> dict:
    """canonical tagged union 形状的 imageGallery block。"""
    images = [{"file_id": str(1000 + index), "order": index} for index in range(image_count)]
    return {
        "kind": "imageGallery",
        "status": "ready",
        "revision": 1,
        "order_key": order_key,
        "node_role": "timeline",
        "payload": {"image_gallery": {"_0": {"images": images}}},
    }


def text_block(text: str = "看图说话", order_key: float = 1000) -> dict:
    return {
        "kind": "text",
        "status": "ready",
        "revision": 1,
        "order_key": order_key,
        "node_role": "timeline",
        "payload": {"text": {"_0": text}},
    }


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
class ImageRunValidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="image-run-user")
        self.other_user = get_user_model().objects.create_user(username="image-run-other")
        self.thread = ChatThread.objects.create(user=self.user, title="image run test")

    def make_image_file(self, *, owner=None, mime_type="image/webp", file_size=1024) -> ManagedFile:
        owner = owner or self.user
        return ManagedFile.objects.create(
            user=owner,
            original_name="chat-image.webp",
            file_ext="webp",
            mime_type=mime_type,
            file_size=file_size,
            is_public=True,
            object_key=f"zhaodkdream/spark_service/chat/image/{uuid.uuid4().hex}.webp",
            storage_type="oss",
        )

    def image_payload(self, *, attachments, gallery_count, client_message_id=None):
        blocks = [text_block(), image_gallery_block(image_count=gallery_count)]
        return canonical_run_payload(
            self.thread.id,
            client_message_id=client_message_id or uuid.uuid4(),
            attachments=attachments,
            blocks=blocks,
        )

    def create_run(self, payload, key="key-1"):
        return RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload=payload,
            idempotency_key=key,
        )

    def test_capability_disabled_rejected(self):
        image_file = self.make_image_file()
        payload = self.image_payload(
            attachments=[{"file_id": str(image_file.id), "type": "image", "order": 0}],
            gallery_count=1,
        )
        with mock.patch(ROUTE_PATCH_TARGET, return_value=make_route(supports_multimodal=False)):
            with self.assertRaises(APIError) as ctx:
                self.create_run(payload)
        self.assertEqual(ctx.exception.msg, "chat_image_capability_unavailable")
        self.assertEqual(ctx.exception.code, 40098)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_route_unresolvable_rejected(self):
        image_file = self.make_image_file()
        payload = self.image_payload(
            attachments=[{"file_id": str(image_file.id), "type": "image", "order": 0}],
            gallery_count=1,
        )
        with mock.patch(ROUTE_PATCH_TARGET, side_effect=RuntimeError("no binding")):
            with self.assertRaises(APIError) as ctx:
                self.create_run(payload)
        self.assertEqual(ctx.exception.msg, "chat_image_capability_unavailable")

    def test_more_than_three_images_rejected(self):
        attachments = [{"file_id": str(9000 + index), "type": "image", "order": index} for index in range(4)]
        payload = self.image_payload(attachments=attachments, gallery_count=4)
        with mock.patch(ROUTE_PATCH_TARGET, return_value=make_route(supports_multimodal=True)):
            with self.assertRaises(APIError) as ctx:
                self.create_run(payload)
        self.assertEqual(ctx.exception.msg, "chat_image_count_exceeded")
        self.assertEqual(ctx.exception.code, 40099)

    def test_invalid_mime_rejected(self):
        image_file = self.make_image_file(mime_type="text/plain")
        payload = self.image_payload(
            attachments=[{"file_id": str(image_file.id), "type": "image", "order": 0}],
            gallery_count=1,
        )
        with mock.patch(ROUTE_PATCH_TARGET, return_value=make_route(supports_multimodal=True)):
            with self.assertRaises(APIError) as ctx:
                self.create_run(payload)
        self.assertEqual(ctx.exception.msg, "chat_image_format_invalid")
        self.assertEqual(ctx.exception.code, 40100)

    def test_oversize_file_rejected(self):
        image_file = self.make_image_file(file_size=10 * 1024 * 1024 + 1)
        payload = self.image_payload(
            attachments=[{"file_id": str(image_file.id), "type": "image", "order": 0}],
            gallery_count=1,
        )
        with mock.patch(ROUTE_PATCH_TARGET, return_value=make_route(supports_multimodal=True)):
            with self.assertRaises(APIError) as ctx:
                self.create_run(payload)
        self.assertEqual(ctx.exception.msg, "chat_image_format_invalid")

    def test_inaccessible_file_rejected_as_not_found(self):
        # 他人私有文件：user_can_access_file 不通过
        image_file = self.make_image_file(owner=self.other_user)
        payload = self.image_payload(
            attachments=[{"file_id": str(image_file.id), "type": "image", "order": 0}],
            gallery_count=1,
        )
        with mock.patch(ROUTE_PATCH_TARGET, return_value=make_route(supports_multimodal=True)):
            with self.assertRaises(APIError) as ctx:
                self.create_run(payload)
        self.assertEqual(ctx.exception.msg, "chat_image_not_found")
        self.assertEqual(ctx.exception.code, 40492)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_missing_file_rejected_as_not_found(self):
        payload = self.image_payload(
            attachments=[{"file_id": "987654321", "type": "image", "order": 0}],
            gallery_count=1,
        )
        with mock.patch(ROUTE_PATCH_TARGET, return_value=make_route(supports_multimodal=True)):
            with self.assertRaises(APIError) as ctx:
                self.create_run(payload)
        self.assertEqual(ctx.exception.msg, "chat_image_not_found")

    def test_gallery_attachment_count_mismatch_rejected(self):
        image_file = self.make_image_file()
        payload = self.image_payload(
            attachments=[{"file_id": str(image_file.id), "type": "image", "order": 0}],
            gallery_count=2,
        )
        with mock.patch(ROUTE_PATCH_TARGET, return_value=make_route(supports_multimodal=True)):
            with self.assertRaises(APIError) as ctx:
                self.create_run(payload)
        self.assertEqual(ctx.exception.msg, "chat_run_request_invalid")
        self.assertEqual(ctx.exception.code, 40091)

    def test_valid_image_run_accepted_and_attachments_in_metadata(self):
        image_file = self.make_image_file()
        attachments = [{"file_id": str(image_file.id), "type": "image", "order": 0}]
        payload = self.image_payload(attachments=attachments, gallery_count=1)
        with mock.patch(ROUTE_PATCH_TARGET, return_value=make_route(supports_multimodal=True)):
            result = self.create_run(payload)
        self.assertFalse(result.replayed)
        self.assertEqual(result.run.status, RunStatus.QUEUED)
        # attachments 写入用户消息 metadata，供消息 wire 原样返回
        self.assertEqual(result.run.user_message.metadata.get("attachments"), attachments)
        gallery = result.run.user_message.blocks.get(kind="imageGallery")
        self.assertIn("image_gallery", gallery.payload)

    def test_attachments_without_type_keep_legacy_behavior(self):
        # iOS 现有 attachments（无 type 字段）：不触发图片校验，无需 mock route
        payload = canonical_run_payload(
            self.thread.id,
            attachments=[{"file_id": "123"}],
        )
        result = self.create_run(payload)
        self.assertFalse(result.replayed)
        self.assertEqual(result.run.user_message.metadata.get("attachments"), [{"file_id": "123"}])

    def test_duplicate_client_message_id_replays_last_run(self):
        client_message_id = uuid.uuid4()
        payload = canonical_run_payload(self.thread.id, client_message_id=client_message_id)
        first = self.create_run(payload, key="key-1")

        # 相同 client_message_id + 相同请求体 + 不同 Idempotency-Key → replay
        replay_payload = canonical_run_payload(self.thread.id, client_message_id=client_message_id)
        second = self.create_run(replay_payload, key="key-2")
        self.assertTrue(second.replayed)
        self.assertEqual(second.run.id, first.run.id)
        self.assertEqual(self.thread.messages.count(), 2)

    def test_duplicate_client_message_id_with_different_payload_conflicts(self):
        client_message_id = uuid.uuid4()
        payload = canonical_run_payload(self.thread.id, content="first", client_message_id=client_message_id)
        self.create_run(payload, key="key-1")

        other = canonical_run_payload(self.thread.id, content="second", client_message_id=client_message_id)
        with self.assertRaises(APIError) as ctx:
            self.create_run(other, key="key-2")
        self.assertEqual(ctx.exception.msg, "chat_idempotency_conflict")
        self.assertEqual(ctx.exception.code, 40992)

    def test_existing_message_without_run_returns_pending(self):
        client_message_id = uuid.uuid4()
        ChatMessage.objects.create(
            user=self.user,
            thread=self.thread,
            role=ChatMessage.Role.USER,
            client_message_id=client_message_id,
            server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=self.thread.created_at,
        )
        payload = canonical_run_payload(self.thread.id, client_message_id=client_message_id)
        with self.assertRaises(APIError) as ctx:
            self.create_run(payload)
        self.assertEqual(ctx.exception.msg, "chat_run_idempotency_pending")
        self.assertEqual(ctx.exception.code, 40980)
        self.assertEqual(ctx.exception.status_code, 409)
