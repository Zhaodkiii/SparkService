from django.apps import apps
from django.test import SimpleTestCase

from chat_sync.ai_models.knowledge import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeCommandReceipt,
    KnowledgeDocument,
    KnowledgeIndexState,
    KnowledgeIndexVersion,
    KnowledgeMutationReceipt,
    KnowledgeRetrievalAudit,
)

KNOWLEDGE_MODELS = (
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeChunk,
    KnowledgeIndexState,
    KnowledgeIndexVersion,
    KnowledgeMutationReceipt,
    KnowledgeCommandReceipt,
    KnowledgeRetrievalAudit,
)


class KnowledgeModelAppRegistryTests(SimpleTestCase):
    """验证工单 D19：知识能力不新增独立 Django App，全部归属现有 chat_sync。"""

    def test_no_separate_knowledge_app_registered(self):
        labels = {config.label for config in apps.get_app_configs()}
        self.assertIn("chat_sync", labels)
        self.assertNotIn("ai_knowledge", labels)
        self.assertNotIn("knowledge", labels)

    def test_models_belong_to_chat_sync_app_label(self):
        for model in KNOWLEDGE_MODELS:
            self.assertEqual(model._meta.app_label, "chat_sync", model.__name__)

    def test_db_table_names_match_ai_knowledge_prefix(self):
        self.assertEqual(KnowledgeBase._meta.db_table, "chat_sync_ai_knowledge_base")
        self.assertEqual(KnowledgeDocument._meta.db_table, "chat_sync_ai_knowledge_document")
        self.assertEqual(KnowledgeChunk._meta.db_table, "chat_sync_ai_knowledge_chunk")
        self.assertEqual(KnowledgeIndexState._meta.db_table, "chat_sync_ai_knowledge_index_state")
        self.assertEqual(KnowledgeMutationReceipt._meta.db_table, "chat_sync_ai_knowledge_mutation_receipt")
        self.assertEqual(KnowledgeIndexVersion._meta.db_table, "chat_sync_ai_knowledge_index_version")
        self.assertEqual(KnowledgeCommandReceipt._meta.db_table, "chat_sync_ai_knowledge_command_receipt")
        self.assertEqual(KnowledgeRetrievalAudit._meta.db_table, "chat_sync_ai_knowledge_retrieval_audit")

    def test_models_registered_via_ai_models_package(self):
        for model in KNOWLEDGE_MODELS:
            self.assertIs(apps.get_model("chat_sync", model.__name__), model)
