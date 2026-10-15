"""File access is scoped to its owner, including business attachment queries."""
from __future__ import annotations


def user_can_access_file(user, file_record) -> bool:
    return bool(
        user and user.is_authenticated and file_record is not None
        and not file_record.is_deleted and file_record.user_id == user.id
    )


def user_can_access_business(user, business_type: str, business_id) -> bool:
    from file_manager.models import ManagedFileBusinessRelation

    if not user or not user.is_authenticated or not business_type:
        return False
    return ManagedFileBusinessRelation.objects.filter(
        user=user, file__user=user, file__is_deleted=False,
        business_type=business_type, business_id=str(business_id or ''),
    ).exists()


def filter_accessible_relation_specs(user, relation_specs):
    filtered = []
    for business_type, business_ids in relation_specs:
        allowed = [str(item) for item in business_ids if item is not None
                   and user_can_access_business(user, business_type, item)]
        if allowed:
            filtered.append((business_type, allowed))
    return filtered
