from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from chat_sync.ai_knowledge.constants import NAMED_BASE_QUOTA
from chat_sync.ai_knowledge.errors import KnowledgeError
from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeBaseKind

DEFAULT_SLOT = 1
DEFAULT_BASE_NAME = "个人知识库"


class KnowledgeBaseService:
    """账号默认知识库的幂等创建与查询；每账号恰好一个默认库。"""

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
            base = KnowledgeBase.objects.filter(user=user, is_default=True, is_deleted=False).first()
            if base is not None:
                return base
            raise

    @staticmethod
    def get_owned(user, base_id, *, include_deleted: bool = False) -> KnowledgeBase:
        queryset = KnowledgeBase.objects.filter(user=user, id=base_id)
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        base = queryset.first()
        if base is None:
            raise KnowledgeError("knowledge_base_not_found", details={"resource_id": str(base_id)})
        return base

    @staticmethod
    def create(*, user, name: str, kind: str = KnowledgeBaseKind.PERSONAL, make_default: bool = False) -> KnowledgeBase:
        cleaned_name = (name or "").strip()[:128] or "未命名知识库"
        if kind not in KnowledgeBaseKind.values:
            kind = KnowledgeBaseKind.PERSONAL
        if kind != KnowledgeBaseKind.PERSONAL:
            kind = KnowledgeBaseKind.PERSONAL
        named_count = KnowledgeBase.objects.filter(user=user, is_deleted=False, is_default=False).count()
        if named_count >= NAMED_BASE_QUOTA:
            raise KnowledgeError("knowledge_base_quota_exceeded", details={"quota": NAMED_BASE_QUOTA})
        with transaction.atomic():
            if make_default:
                KnowledgeBase.objects.filter(user=user, is_default=True, is_deleted=False).update(
                    is_default=False,
                    default_slot=None,
                    revision=models_F_revision(),
                    server_updated_at=timezone.now(),
                )
            base = KnowledgeBase.objects.create(
                user=user,
                name=cleaned_name,
                kind=kind,
                is_default=make_default,
                default_slot=DEFAULT_SLOT if make_default else None,
            )
        return base

    @staticmethod
    def update(user, base_id, *, revision: int | None, name: str | None = None, make_default: bool | None = None) -> KnowledgeBase:
        with transaction.atomic():
            base = KnowledgeBase.objects.select_for_update().filter(user=user, id=base_id, is_deleted=False).first()
            if base is None:
                raise KnowledgeError("knowledge_base_not_found", details={"resource_id": str(base_id)})
            if revision is not None and int(revision) != base.revision:
                raise KnowledgeError(
                    "knowledge_base_revision_conflict",
                    details={"resource_id": str(base.id), "server_revision": base.revision},
                )
            if name is not None:
                base.name = name.strip()[:128] or base.name
            if make_default is True and not base.is_default:
                KnowledgeBase.objects.filter(user=user, is_default=True, is_deleted=False).exclude(pk=base.pk).update(
                    is_default=False,
                    default_slot=None,
                )
                base.is_default = True
                base.default_slot = DEFAULT_SLOT
            base.revision += 1
            base.save()
        return base

    @staticmethod
    def soft_delete(*, user, base_id, revision: int | None) -> KnowledgeBase:
        with transaction.atomic():
            base = KnowledgeBase.objects.select_for_update().filter(user=user, id=base_id, is_deleted=False).first()
            if base is None:
                raise KnowledgeError("knowledge_base_not_found", details={"resource_id": str(base_id)})
            if base.is_default:
                raise KnowledgeError("knowledge_base_default_undeletable")
            if revision is not None and int(revision) != base.revision:
                raise KnowledgeError(
                    "knowledge_base_revision_conflict",
                    details={"resource_id": str(base.id), "server_revision": base.revision},
                )
            base.is_deleted = True
            base.deleted_at = timezone.now()
            base.is_default = False
            base.default_slot = None
            base.revision += 1
            base.save()
        return base


def models_F_revision():
    from django.db.models import F

    return F("revision") + 1
