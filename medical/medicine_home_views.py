from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.http_cache import build_etag, normalize_etag
from common.response import error_response, success_response
from medical.models import MedicineBox, MedicationRecord, Member
from medical.serializers import MedicineBoxSerializer
from medical.services.member_permission_gate import MemberPermissionGate
from medical.services.medicine_cabinet_service import family_medicine_cabinet_queryset
from medical.services.medicine_home_service import build_home_snapshot, serialize_medicine_box


def entry_member_id(request):
    raw = request.query_params.get("member_id") or request.data.get("member_id")
    try:
        return int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


class MedicineHomeAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member_id = entry_member_id(request)
        if member_id is None:
            return error_response(msg="member_id_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        try:
            payload = build_home_snapshot(request.user, member_id, search=request.query_params.get("search", ""))
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        etag_payload = dict(payload)
        etag_payload.pop("generated_at", None)
        etag = build_etag(etag_payload)
        if normalize_etag(request.headers.get("If-None-Match")) == etag:
            return Response(status=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
        response = success_response(payload, msg="success", code=0)
        response["ETag"] = etag
        response["Cache-Control"] = "private, max-age=30"
        return response


class MedicineHomeSearchAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member_id = entry_member_id(request)
        query = (request.query_params.get("q") or "").strip()
        if member_id is None or not query:
            return error_response(msg="member_id_and_q_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        try:
            boxes = family_medicine_cabinet_queryset(user=request.user, entry_member_id=member_id).filter(medicine_name__icontains=query)[:50]
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        return success_response({"query": query, "items": [serialize_medicine_box(box) for box in boxes]}, msg="success", code=0)


class MedicineBoxStocktakeAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, box_id):
        try:
            quantity = Decimal(str(request.data.get("quantity")))
        except (TypeError, ValueError, InvalidOperation):
            return error_response(msg="quantity_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        if quantity < 0 or quantity.as_tuple().exponent < -2:
            return error_response(msg="quantity_must_be_non_negative", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            box = MedicineBox.objects.select_for_update().filter(id=box_id, is_deleted=False).first()
            if box is None:
                return error_response(msg="medicine_box_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
            member_id = box.member_id or Member.objects.filter(user_id=box.user_id, is_deleted=False).values_list("id", flat=True).first()
            try:
                MemberPermissionGate.require_edit(user=request.user, member_id=member_id)
            except PermissionError:
                return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
            box.total_quantity = quantity
            extra = dict(box.extra or {})
            extra["home_meta"] = {**(extra.get("home_meta") or {}), "last_stocktake_at": timezone.now().isoformat()}
            box.extra = extra
            box.save(update_fields=["total_quantity", "extra", "updated_at"])
        return success_response(MedicineBoxSerializer(box, context={"request": request}).data, msg="updated", code=0)


class MedicationRecordActionAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, record_id, action):
        targets = {"mark-taken": MedicationRecord.Status.TAKEN, "mark-skipped": MedicationRecord.Status.SKIPPED, "snooze": MedicationRecord.Status.SNOOZED}
        if action not in targets:
            return error_response(msg="unsupported_action", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            record = MedicationRecord.objects.select_for_update().select_related("plan").filter(id=record_id, user=request.user, is_deleted=False).first()
            if record is None:
                return error_response(msg="medication_record_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
            try:
                MemberPermissionGate.require_edit(user=request.user, member_id=record.member_id)
            except PermissionError:
                return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
            target = targets[action]
            previous = record.status
            if previous != target:
                record.status = target
                record.taken_at = timezone.now() if target == MedicationRecord.Status.TAKEN else None
                record.save(update_fields=["status", "taken_at", "updated_at"])
                if target == MedicationRecord.Status.TAKEN and previous != MedicationRecord.Status.TAKEN and record.plan and record.plan.medicine_box_id and record.plan.dose_value:
                    box = MedicineBox.objects.select_for_update().filter(id=record.plan.medicine_box_id, user=request.user, is_deleted=False).first()
                    if box and box.total_quantity is not None:
                        box.total_quantity = max(Decimal("0"), box.total_quantity - record.plan.dose_value).quantize(Decimal("0.01"))
                        box.save(update_fields=["total_quantity", "updated_at"])
        return success_response({"id": record.id, "status": record.status, "taken_at": record.taken_at}, msg="updated", code=0)
