from django.db.models import Q

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
    return (
        ManagedFile.objects.filter(
            user=user,
            is_deleted=False,
            business_relations__business_type=business_type,
            business_relations__business_id=str(business_id or ""),
        )
        .distinct()
        .order_by("-created_at")
    )


def files_for_businesses(user, relation_specs):
    combined = _relation_q(relation_specs, prefix="business_relations__")
    queryset = ManagedFile.objects.filter(user=user, is_deleted=False)
    if combined is None:
        return queryset.none()
    return queryset.filter(combined).distinct()


def relation_fingerprint(user, relation_specs):
    combined = _relation_q(relation_specs)
    if combined is None:
        return []
    return list(
        ManagedFileBusinessRelation.objects.filter(user=user, file__is_deleted=False)
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
