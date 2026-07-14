from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from medical.models import MedicationPlan, MedicationRecord, Member
from medical.services.member_permission_gate import MemberPermissionGate
from medical.services.medicine_cabinet_service import family_medicine_cabinet_queryset


def _date(value):
    return value.isoformat() if value else None


def _datetime(value):
    return value.isoformat() if value else None


def serialize_medicine_box(box):
    return {
        "id": box.id,
        "member_id": box.member_id,
        "medicine_name": box.medicine_name,
        "medicine_type": box.medicine_type,
        "brand_name": box.brand_name,
        "dosage_form": box.dosage_form,
        "strength": box.strength,
        "dose_unit": box.dose_unit,
        "total_quantity": float(box.total_quantity) if box.total_quantity is not None else None,
        "expire_date": _date(box.expire_date),
        "notes": box.notes,
        "extra": box.extra or {},
        "updated_at": _datetime(box.updated_at),
    }


def build_home_snapshot(user, entry_member_id, *, search=""):
    boxes = list(family_medicine_cabinet_queryset(user=user, entry_member_id=entry_member_id).select_related("member"))
    if search.strip():
        query = search.strip().casefold()
        boxes = [box for box in boxes if query in box.medicine_name.casefold()]

    members = MemberPermissionGate.filter_qs(Member.objects.filter(is_deleted=False), user, member_field="id")
    member_ids = list(members.values_list("id", flat=True))
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(tomorrow, datetime.min.time()))
    plans = list(
        MedicationPlan.objects.filter(
            user=user,
            member_id__in=member_ids,
            is_deleted=False,
            is_archived=False,
            status__in=[MedicationPlan.Status.ACTIVE, MedicationPlan.Status.AS_NEEDED],
            start_date__lte=today,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
    )
    records = {
        record.plan_id: record
        for record in MedicationRecord.objects.filter(
            user=user,
            member_id__in=member_ids,
            is_deleted=False,
            scheduled_at__gte=start,
            scheduled_at__lt=end,
        )
    }
    expiring_limit = today + timedelta(days=30)
    expiring = [box for box in boxes if box.expire_date and box.expire_date <= expiring_limit]
    low_stock = [box for box in boxes if box.total_quantity is not None and box.total_quantity <= 0]
    pending = [record for record in records.values() if record.status in {MedicationRecord.Status.SCHEDULED, MedicationRecord.Status.SNOOZED}]
    medication_items = []
    for plan in plans:
        record = records.get(plan.id)
        if record is None:
            continue
        medication_items.append({
            "id": plan.id,
            "member_id": plan.member_id,
            "medicine_box_id": plan.medicine_box_id,
            "drug_name": plan.drug_name,
            "dose_per_time": plan.dose_per_time,
            "dose_unit": plan.dose_unit,
            "frequency_text": plan.frequency_text,
            "status": plan.status,
            "record": {
                "id": record.id,
                "scheduled_at": _datetime(record.scheduled_at),
                "taken_at": _datetime(record.taken_at),
                "status": record.status,
                "planned_dose": record.planned_dose,
            },
        })
    return {
        "version": 1,
        "generated_at": timezone.now().isoformat(),
        "entry_member_id": entry_member_id,
        "members": [{"id": member.id, "name": member.name, "avatar_url": member.avatar_url} for member in members],
        "summary": {
            "medicine_count": len(boxes),
            "expiring_count": len(expiring),
            "low_stock_count": len(low_stock),
            "today_pending_count": len(pending),
            "today_taken_count": sum(record.status == MedicationRecord.Status.TAKEN for record in records.values()),
        },
        "medicines": [serialize_medicine_box(box) for box in boxes[:100]],
        "expiring_medicines": [serialize_medicine_box(box) for box in expiring[:20]],
        "low_stock_medicines": [serialize_medicine_box(box) for box in low_stock[:20]],
        "today_medications": medication_items[:50],
    }
