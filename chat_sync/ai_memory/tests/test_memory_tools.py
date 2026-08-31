import uuid

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase

from chat_sync.ai_models.memory import AIMemory
from chat_sync.ai_runtime.tools.adapters.read_memory import ReadMemoryTool
from chat_sync.ai_runtime.tools.adapters.write_memory import WriteMemoryTool
from chat_sync.ai_runtime.tools.policy import ToolExecutionContext, ToolPolicy
from chat_sync.ai_runtime.tools.registry import build_server_tool_registry
from chat_sync.ai_runtime.tools.server_names import SparkServerToolName


def _context(user_id: int, member_id=None):
    return ToolExecutionContext(
        run_id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        user_id=user_id,
        member_id=member_id,
    )


class MemoryToolTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="mem-tools")
        self.other = get_user_model().objects.create_user(username="mem-tools-other")

    def test_registry_includes_memory_tools_with_extended_policy(self):
        registry = build_server_tool_registry()
        read_entry = registry.get(SparkServerToolName.READ_MEMORY.value)
        write_entry = registry.get(SparkServerToolName.WRITE_MEMORY.value)
        self.assertIsNotNone(read_entry)
        self.assertIsNotNone(write_entry)
        self.assertEqual(read_entry.policy.risk, "personal_data_read")
        self.assertEqual(write_entry.policy.risk, "personal_data_write")
        self.assertEqual(write_entry.policy.side_effect, "memory_write")
        write_entry.policy.validate()
        with self.assertRaises(ValueError):
            ToolPolicy("other_write", risk="personal_data_write", side_effect="memory_write").validate()
        schema = write_entry.schema
        properties = schema.get("function", {}).get("parameters", {}).get("properties") or schema.get("parameters", {}).get("properties") or {}
        self.assertIn("text", properties)
        self.assertNotIn("target_id", properties)
        self.assertNotEqual(properties.get("op", {}).get("enum"), ["add", "edit"])

    def test_write_add_is_idempotent_on_same_text(self):
        tool = WriteMemoryTool()
        context = _context(self.user.id)
        first = async_to_sync(tool.execute)(text="以后请用中文回答。", _execution_context=context)
        second = async_to_sync(tool.execute)(text="以后请用中文回答。", _execution_context=context)
        self.assertTrue(first.success)
        self.assertEqual(first.metadata["action"], "added")
        self.assertEqual(second.metadata["action"], "duplicate")
        self.assertEqual(AIMemory.objects.filter(user=self.user, is_deleted=False).count(), 1)

    def test_write_rejects_health_and_credentials(self):
        tool = WriteMemoryTool()
        context = _context(self.user.id)
        health = async_to_sync(tool.execute)(text="你可能有高血压。", _execution_context=context)
        secret = async_to_sync(tool.execute)(text="帮我记住验证码 123456。", _execution_context=context)
        self.assertEqual(health.metadata["error_code"], "memory_invalid_preference")
        self.assertEqual(secret.metadata["error_code"], "memory_invalid_preference")
        self.assertEqual(AIMemory.objects.filter(user=self.user).count(), 0)

    def test_write_does_not_edit_existing_memory(self):
        tool = WriteMemoryTool()
        context = _context(self.user.id)
        added = async_to_sync(tool.execute)(text="回答尽量简短。", _execution_context=context)
        second = async_to_sync(tool.execute)(text="回答尽量详细。", _execution_context=context)
        self.assertTrue(added.success)
        self.assertTrue(second.success)
        self.assertEqual(second.metadata["action"], "added")
        self.assertEqual(AIMemory.objects.filter(user=self.user, is_deleted=False).count(), 2)
        original = AIMemory.objects.get(id=added.metadata["entry_id"])
        self.assertEqual(original.content, "回答尽量简短。")
        self.assertEqual(original.revision, 1)

    def test_read_memory_formats_slots_and_skips_when_empty(self):
        tool = ReadMemoryTool()
        empty = async_to_sync(tool.execute)(_execution_context=_context(self.user.id))
        self.assertTrue(empty.success)
        self.assertIn("没有可读取", empty.content)
        async_to_sync(WriteMemoryTool().execute)(text="以后请用中文回答。", _execution_context=_context(self.user.id))
        filled = async_to_sync(tool.execute)(_execution_context=_context(self.user.id))
        self.assertIn("# Preferences", filled.content)
        self.assertTrue(filled.metadata["entry_ids"])

    def test_read_does_not_leak_other_account(self):
        async_to_sync(WriteMemoryTool().execute)(text="称呼我为小华。", _execution_context=_context(self.user.id))
        other_result = async_to_sync(ReadMemoryTool().execute)(_execution_context=_context(self.other.id))
        self.assertEqual(other_result.metadata.get("count") or 0, 0)
        self.assertFalse(other_result.metadata.get("entry_ids"))

    def test_public_projection_does_not_leak_memory_content(self):
        from chat_sync.ai_runtime.tools.public_projector import public_error, safe_source_refs

        secret = "称呼我为小华。"
        refs = safe_source_refs(
            [
                {
                    "source_id": "mem-1",
                    "type": "memory",
                    "content": secret,
                    "content_hash": "abc",
                    "metadata": {"layer": "L3", "document_key": "preferences"},
                }
            ]
        )
        self.assertEqual(refs[0]["source_id"], "mem-1")
        self.assertEqual(refs[0]["type"], "memory")
        self.assertNotIn("content", refs[0])
        self.assertNotIn(secret, str(refs))
        projected = public_error("memory_disabled")
        self.assertEqual(projected["code"], "tool_unavailable")
        self.assertNotIn(secret, str(projected))
