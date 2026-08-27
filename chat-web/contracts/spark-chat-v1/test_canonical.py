"""Strict canonical block contract tests (CHAT-DATA-026)."""
from __future__ import annotations

from django.test import SimpleTestCase

from chat_sync.contracts import (
    BLOCK_KINDS,
    KIND_SEARCH_SUMMARY,
    KIND_TOOL,
    KIND_TOOL_QUESTION_CARDS,
    BlockContractError,
    assistant_status_payload,
    decode_block,
    decode_payload,
    error_payload,
    payload_kind,
    payload_text,
    search_summary_payload,
    text_payload,
    tool_payload,
    tool_presentation_kind,
    tool_question_cards_payload,
    tool_result_presentation_payload,
    validate_anchor,
    validate_node_role,
)


class BlockKindTests(SimpleTestCase):
    def test_36_kinds_are_declared(self):
        self.assertEqual(len(BLOCK_KINDS), 36)
        self.assertIn(KIND_TOOL, BLOCK_KINDS)
        self.assertIn(KIND_SEARCH_SUMMARY, BLOCK_KINDS)
        self.assertNotIn("toolCall", BLOCK_KINDS)
        self.assertNotIn("toolResult", BLOCK_KINDS)


class PayloadUnionTests(SimpleTestCase):
    def test_text_payload_is_tagged_union(self):
        self.assertEqual(text_payload("你好"), {"text": {"_0": "你好"}})

    def test_tool_payload_wraps_inner(self):
        self.assertEqual(
            tool_payload("读取健康档案", '{"sections": ["过敏史"]}'),
            {"tool": {"_0": {"name": "读取健康档案", "content": '{"sections": ["过敏史"]}'}}},
        )

    def test_tool_payload_uses_ios_snake_case_arguments_key(self):
        self.assertIn(
            "invocation_arguments",
            tool_payload("t", "c", {"k": "v"})["tool"]["_0"],
        )

    def test_search_summary_payload_ios_wire_shape(self):
        payload = search_summary_payload("读取健康档案", "已读取 1 个分区")
        inner = payload["search_summary"]["_0"]
        self.assertEqual(inner["provider_name"], "读取健康档案")
        self.assertEqual(inner["query"], "已读取 1 个分区")
        self.assertEqual(inner["references"], [])
        self.assertEqual(inner["total_estimated_matches"], None)

    def test_assistant_status_and_error_payloads(self):
        self.assertEqual(error_payload("boom"), {"error": {"_0": "boom"}})
        self.assertEqual(
            assistant_status_payload("interrupted", "m"),
            {"assistant_status_card": {"_0": {"type": "interrupted", "message": "m"}}},
        )

    def test_payload_kind_is_strict(self):
        self.assertEqual(payload_kind({"text": {"_0": "x"}}), "text")
        self.assertIsNone(payload_kind({"text": "x"}))
        self.assertIsNone(payload_kind({"id": "1", "kind": "text", "text": "x"}))
        self.assertIsNone(payload_kind({"text": {"_0": "x"}, "tool": {"_0": {}}}))
        self.assertIsNone(payload_kind("not a dict"))
        self.assertIsNone(payload_kind(None))

    def test_payload_text_only_unwraps_canonical(self):
        self.assertEqual(payload_text({"text": {"_0": "回答"}}), "回答")
        self.assertEqual(payload_text({"text": "回答"}), "")
        self.assertEqual(payload_text(None), "")
        self.assertEqual(payload_text({"tool": {"_0": {"name": "t"}}}), "")


class DecodePayloadTests(SimpleTestCase):
    def test_valid_returns_kind_and_value(self):
        decoded = decode_payload({"tool": {"_0": {"name": "t", "content": "c"}}})
        self.assertEqual(decoded.kind, "tool")
        self.assertEqual(decoded.value, {"name": "t", "content": "c"})

    def test_missing_discriminator_rejects(self):
        with self.assertRaises(BlockContractError) as ctx:
            decode_payload({"id": "1", "text": "x"})
        self.assertEqual(ctx.exception.code, "chat_block_payload_invalid")

    def test_flat_text_rejects(self):
        with self.assertRaises(BlockContractError) as ctx:
            decode_payload({"text": "x"})
        self.assertEqual(ctx.exception.code, "chat_block_payload_invalid")

    def test_ambiguous_rejects(self):
        with self.assertRaises(BlockContractError) as ctx:
            decode_payload({"text": {"_0": "x"}, "tool": {"_0": {}}})
        self.assertEqual(ctx.exception.code, "chat_block_payload_ambiguous")

    def test_missing_associated_value_rejects(self):
        with self.assertRaises(BlockContractError) as ctx:
            decode_payload({"text": {}})
        self.assertEqual(ctx.exception.code, "chat_block_payload_invalid")


class DecodeBlockTests(SimpleTestCase):
    def _tool_block(self):
        return {
            "kind": "tool",
            "node_role": "tool",
            "payload": {"tool": {"_0": {"name": "t", "content": "c"}}},
        }

    def test_valid_block(self):
        block = decode_block(self._tool_block())
        self.assertEqual(block.kind, "tool")
        self.assertEqual(block.node_role, "tool")

    def test_kind_mismatch_rejects(self):
        with self.assertRaises(BlockContractError) as ctx:
            decode_block({**self._tool_block(), "kind": "text"})
        self.assertEqual(ctx.exception.code, "chat_block_kind_mismatch")

    def test_missing_kind_is_derived_from_payload(self):
        raw = self._tool_block()
        raw.pop("kind")
        self.assertEqual(decode_block(raw).kind, "tool")

    def test_unknown_node_role_rejects(self):
        with self.assertRaises(BlockContractError) as ctx:
            decode_block({**self._tool_block(), "node_role": "timeline"})
        self.assertEqual(ctx.exception.code, "chat_block_node_role_invalid")

    def test_missing_node_role_rejects(self):
        raw = self._tool_block()
        raw.pop("node_role")
        with self.assertRaises(BlockContractError) as ctx:
            decode_block(raw)
        self.assertEqual(ctx.exception.code, "chat_block_node_role_invalid")

    def test_invalid_anchor_rejects(self):
        with self.assertRaises(BlockContractError) as ctx:
            decode_block({**self._tool_block(), "anchor": {"type": "nonsense"}})
        self.assertEqual(ctx.exception.code, "chat_block_anchor_invalid")

    def test_tool_anchor_requires_value(self):
        with self.assertRaises(BlockContractError):
            decode_block({**self._tool_block(), "anchor": {"type": "toolCall"}})


class NodeRoleValidationTests(SimpleTestCase):
    def test_valid_roles(self):
        self.assertEqual(validate_node_role("timeline"), "timeline")
        self.assertEqual(validate_node_role("tool"), "tool")
        self.assertEqual(validate_node_role("toolPresentation"), "toolPresentation")

    def test_unknown_role_rejects(self):
        for value in ("", "bogus", "content", "toolExecution", "interaction"):
            with self.assertRaises(BlockContractError):
                validate_node_role(value)


class AnchorValidationTests(SimpleTestCase):
    def test_value_less_anchor_ok(self):
        validate_anchor({"type": "messageStart"})
        validate_anchor({"type": "messageEnd"})

    def test_value_anchor_requires_string_value(self):
        validate_anchor({"type": "toolCall", "value": "call_1"})
        with self.assertRaises(BlockContractError):
            validate_anchor({"type": "toolCall"})


class ToolPresentationRegistryTests(SimpleTestCase):
    def test_default_is_search_summary(self):
        self.assertEqual(tool_presentation_kind("some_tool"), KIND_SEARCH_SUMMARY)

    def test_result_projection_is_search_summary_not_text(self):
        payload = tool_result_presentation_payload(
            tool_name="read_source",
            display_name="读取参考资料",
            result_preview="已读取参考资料",
            source_refs=[{"source_id": "exam_report:42", "type": "examination_report", "title": "体检报告"}],
        )
        self.assertIn("search_summary", payload)
        self.assertNotIn("text", payload)

    def test_references_prefer_friendly_title_and_map_type(self):
        payload = tool_result_presentation_payload(
            tool_name="read_source",
            display_name="读取参考资料",
            result_preview="已读取参考资料",
            source_refs=[{"source_id": "s1", "type": "examination_report", "title": "报告A"}],
        )
        inner = payload["search_summary"]["_0"]
        self.assertEqual(inner["provider_name"], "读取参考资料")
        self.assertEqual(inner["query"], "已读取参考资料")
        self.assertEqual(inner["references"][0]["title"], "报告A")
        self.assertEqual(inner["references"][0]["source_name"], "examination_report")

    def test_result_projection_falls_back_without_preview(self):
        payload = tool_result_presentation_payload(
            tool_name="query_member_profile",
            display_name="读取健康档案",
            result_preview=None,
        )
        inner = payload["search_summary"]["_0"]
        self.assertEqual(inner["query"], "读取健康档案")
        self.assertEqual(inner["references"], [])


class ToolQuestionCardsPayloadTests(SimpleTestCase):
    def test_payload_is_tagged_union_without_raw_arguments(self):
        payload = tool_question_cards_payload(
            run_id="11111111-1111-1111-1111-111111111111",
            interaction_id="22222222-2222-2222-2222-222222222222",
            interaction_key="run:1:tool:call_ask_1:stage:0",
            tool_call_id="call_ask_1",
            tool_name="ask_user",
            tool_version="v1",
            schema_version=2,
            status="pending",
            question_ids=["q1"],
            request={"questions": [{"id": "q1", "prompt": "分析几天？"}]},
            expires_at="2026-08-28T00:00:00+00:00",
        )
        self.assertEqual(payload_kind(payload), KIND_TOOL_QUESTION_CARDS)
        inner = payload["tool_question_cards"]["_0"]
        self.assertEqual(inner["interaction_id"], "22222222-2222-2222-2222-222222222222")
        self.assertEqual(inner["question_ids"], ["q1"])
        self.assertNotIn("arguments", inner)
        self.assertNotIn("result_content", inner)
