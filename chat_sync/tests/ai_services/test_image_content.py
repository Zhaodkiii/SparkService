"""Runtime 多模态图片内容组装测试（CHAT-WEB-029）。"""

from __future__ import annotations

import base64
import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from PIL import Image

from chat_sync.ai_services.context.context_builder import ContextBuildError
from chat_sync.ai_services.context.token_counter import IMAGE_PART_TOKEN_ESTIMATE, count_message, count_tokens
from chat_sync.ai_services.image_content import (
    IMAGE_ONLY_PROMPT,
    build_image_content_parts,
    build_multimodal_user_content,
    has_image_attachments,
)
from chat_sync.ai_services.prompt_assembler import assemble_messages
from file_manager.models import ManagedFile
from file_manager.services.oss_object_service import OssUploadError

GET_BYTES_PATCH_TARGET = "chat_sync.ai_services.image_content.get_bytes"


def make_image_bytes(fmt="WEBP", size=(48, 48), color=(30, 160, 60)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


class ImageContentPartsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="image-content-user")

    def make_image_file(self, *, mime_type="image/webp") -> ManagedFile:
        return ManagedFile.objects.create(
            user=self.user,
            original_name="chat-image.webp",
            file_ext="webp",
            mime_type=mime_type,
            file_size=128,
            is_public=True,
            object_key=f"zhaodkdream/spark_service/chat/image/{uuid.uuid4().hex}.webp",
            storage_type="oss",
        )

    def make_run(self, attachments) -> SimpleNamespace:
        return SimpleNamespace(request_snapshot={"attachments": attachments})

    def test_build_parts_generates_data_url(self):
        image_file = self.make_image_file()
        raw = make_image_bytes(fmt="WEBP")
        run = self.make_run([
            {"file_id": str(image_file.id), "type": "image", "order": 0, "mime_type": "image/webp"},
        ])
        with mock.patch(GET_BYTES_PATCH_TARGET, side_effect=lambda *, object_key, max_bytes: raw):
            parts = build_image_content_parts(user=self.user, run=run)
        self.assertEqual(len(parts), 1)
        expected_url = f"data:image/webp;base64,{base64.b64encode(raw).decode('ascii')}"
        self.assertEqual(parts[0], {"type": "image_url", "image_url": {"url": expected_url}})

    def test_build_parts_ordered_by_order_field(self):
        first = self.make_image_file()
        second = self.make_image_file()
        raw = make_image_bytes(fmt="WEBP")
        run = self.make_run([
            {"file_id": str(second.id), "type": "image", "order": 1},
            {"file_id": str(first.id), "type": "image", "order": 0},
        ])
        calls = []

        def fake_get_bytes(*, object_key, max_bytes):
            calls.append(object_key)
            return raw

        with mock.patch(GET_BYTES_PATCH_TARGET, side_effect=fake_get_bytes):
            parts = build_image_content_parts(user=self.user, run=run)
        self.assertEqual(len(parts), 2)
        self.assertEqual(calls, [first.object_key, second.object_key])

    def test_read_failure_raises_context_build_error(self):
        image_file = self.make_image_file()
        run = self.make_run([{"file_id": str(image_file.id), "type": "image", "order": 0}])
        with mock.patch(GET_BYTES_PATCH_TARGET, side_effect=OssUploadError("oss_get_failed")):
            with self.assertRaises(ContextBuildError) as ctx:
                build_image_content_parts(user=self.user, run=run)
        self.assertEqual(ctx.exception.code, "chat_image_read_failed")

    def test_missing_file_raises_context_build_error(self):
        run = self.make_run([{"file_id": "987654321", "type": "image", "order": 0}])
        with self.assertRaises(ContextBuildError) as ctx:
            build_image_content_parts(user=self.user, run=run)
        self.assertEqual(ctx.exception.code, "chat_image_read_failed")

    def test_undecodable_bytes_raise_context_build_error(self):
        image_file = self.make_image_file()
        run = self.make_run([{"file_id": str(image_file.id), "type": "image", "order": 0}])
        with mock.patch(GET_BYTES_PATCH_TARGET, side_effect=lambda *, object_key, max_bytes: b"junk-bytes"):
            with self.assertRaises(ContextBuildError) as ctx:
                build_image_content_parts(user=self.user, run=run)
        self.assertEqual(ctx.exception.code, "chat_image_read_failed")

    def test_image_only_injects_prompt(self):
        image_file = self.make_image_file()
        raw = make_image_bytes(fmt="WEBP")
        run = self.make_run([{"file_id": str(image_file.id), "type": "image", "order": 0}])
        with mock.patch(GET_BYTES_PATCH_TARGET, side_effect=lambda *, object_key, max_bytes: raw):
            content = build_multimodal_user_content(user=self.user, run=run, current_text="")
        self.assertEqual(content[0], {"type": "text", "text": IMAGE_ONLY_PROMPT})
        self.assertEqual(content[1]["type"], "image_url")

    def test_text_preserved_when_present(self):
        image_file = self.make_image_file()
        raw = make_image_bytes(fmt="WEBP")
        run = self.make_run([{"file_id": str(image_file.id), "type": "image", "order": 0}])
        with mock.patch(GET_BYTES_PATCH_TARGET, side_effect=lambda *, object_key, max_bytes: raw):
            content = build_multimodal_user_content(user=self.user, run=run, current_text="看看这张图")
        self.assertEqual(content[0], {"type": "text", "text": "看看这张图"})
        self.assertEqual(len(content), 2)

    def test_has_image_attachments(self):
        self.assertTrue(has_image_attachments({"attachments": [{"type": "image", "file_id": "1"}]}))
        self.assertFalse(has_image_attachments({"attachments": [{"file_id": "1"}]}))
        self.assertFalse(has_image_attachments({}))
        self.assertFalse(has_image_attachments(None))


class MultimodalAssembleTests(TestCase):
    def test_assemble_messages_accepts_list_content(self):
        parts = [
            {"type": "text", "text": "看图"},
            {"type": "image_url", "image_url": {"url": "data:image/webp;base64,AAAA"}},
        ]
        messages, _ = assemble_messages(blocks=[], history=[], current_text=parts)
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], parts)

    def test_assemble_messages_str_content_unchanged(self):
        messages, _ = assemble_messages(blocks=[], history=[{"role": "user", "content": "hi"}], current_text="hello")
        self.assertEqual(messages[-1]["content"], "hello")
        self.assertTrue(all(isinstance(item["content"], str) for item in messages))

    def test_count_message_with_image_parts(self):
        text = "请分析这张图片"
        parts = [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": "data:image/webp;base64,AAAA"}},
            {"type": "image_url", "image_url": {"url": "data:image/webp;base64,BBBB"}},
        ]
        counted = count_message({"role": "user", "content": parts})
        expected = count_tokens(text).count + 4 + 2 * IMAGE_PART_TOKEN_ESTIMATE
        self.assertEqual(counted.count, expected)

    def test_count_message_str_content_unchanged(self):
        counted = count_message({"role": "user", "content": "hello"})
        self.assertEqual(counted.count, count_tokens("hello").count + 4)
