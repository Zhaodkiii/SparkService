from __future__ import annotations

from django.db import IntegrityError, transaction

from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeBaseKind

DEFAULT_SLOT = 1
DEFAULT_BASE_NAME = "个人知识库"


class KnowledgeBaseService:
    """账号默认知识库的幂等创建与查询；V1 每账号恰好一个默认库。"""

    @staticmethod
    def get_or_create_default(user) -> KnowledgeBase:
        base = KnowledgeBase.objects.filter(user=user, is_default=True, is_deleted=False).first()
        if base is not None:
            return base

        try:
            with transaction.atomic():
                return KnowledgeBase.objects.create(
                    user=user,
                    name=DEFAULT_BASE_NAME,
                    kind=KnowledgeBaseKind.PERSONAL,
                    is_default=True,
                    default_slot=DEFAULT_SLOT,
                )
        except IntegrityError:
            # (user, default_slot) 唯一约束在并发请求下会拒绝第二次插入；
            # 重新查询即可拿到并发对手已经创建成功的那一条，保证“恰好一个默认库”。
            base = KnowledgeBase.objects.filter(user=user, is_default=True, is_deleted=False).first()
            if base is not None:
                return base
            raise
