from django.db.models import Q

from file_manager.business_access import (
    filter_accessible_relation_specs,
    user_can_access_business,
    user_can_access_file,
)
from file_manager.models import ManagedFile, ManagedFileBusinessRelation


def bind_file_to_business(user, file_record, business_type, business_id=""):
    if not business_type:
        return None
    relation, _ = ManagedFileBusinessRelation.objects.get_or_create(
        file=file_record,
        user=user,
        business_type=business_type,
        business_id=str(business_id or ""),
    )
    return relation


def bind_files_to_business(user, business_type, business_id, file_ids):
    if not file_ids or not business_type:
        return 0

    files = ManagedFile.objects.filter(user=user, id__in=file_ids, is_deleted=False).only("id", "user_id")
    relations = [
        ManagedFileBusinessRelation(
            file=file_record,
            user=user,
            business_type=business_type,
            business_id=str(business_id or ""),
        )
        for file_record in files
    ]
    if not relations:
        return 0
    created = ManagedFileBusinessRelation.objects.bulk_create(relations, ignore_conflicts=True)
    return len(created)


def files_for_business(user, business_type, business_id):
    """
    返回绑定到某业务实体的附件。

    文件元数据仍归属上传者（``ManagedFile.user``），但任意对该成员有绑定权限的用户均可读取。
    """
    if not user_can_access_business(user, business_type, business_id):
        return ManagedFile.objects.none()
    return (
        ManagedFile.objects.filter(
            is_deleted=False,
            business_relations__business_type=business_type,
            business_relations__business_id=str(business_id or ""),
        )
        .distinct()
        .order_by("-created_at")
    )


def files_for_businesses(user, relation_specs):
    accessible_specs = filter_accessible_relation_specs(user, relation_specs)
    combined = _relation_q(accessible_specs, prefix="business_relations__")
    if combined is None:
        return ManagedFile.objects.none()
    return ManagedFile.objects.filter(is_deleted=False).filter(combined).distinct()


def relation_fingerprint(user, relation_specs):
    accessible_specs = filter_accessible_relation_specs(user, relation_specs)
    combined = _relation_q(accessible_specs)
    if combined is None:
        return []
    return list(
        ManagedFileBusinessRelation.objects.filter(file__is_deleted=False)
        .filter(combined)
        .values_list("file_id", "updated_at")
    )


def _relation_q(relation_specs, prefix=""):
    combined = None
    for business_type, business_ids in relation_specs:
        ids = [str(item) for item in business_ids if item is not None]
        if not ids:
            continue
        query = Q(**{f"{prefix}business_type": business_type, f"{prefix}business_id__in": ids})
        combined = query if combined is None else combined | query
    return combined
