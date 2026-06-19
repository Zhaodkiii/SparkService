import logging
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import signing
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.http_cache import build_etag, normalize_etag
from common.response import error_response, success_response
from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    MedicineBox,
    MedicationPlan,
    MedicationRecord,
    MedExamDetail,
    MedicalCase,
    ModelChangeLog,
    Member,
    MemberMedicalProfile,
    MemberModuleSetting,
    MemberShareInvite,
    Prescription,
    Surgery,
    Symptom,
    UserMemberBinding,
    Visit,
)
from medical.services.member_permission_gate import MemberPermissionGate
from medical.serializers import (
    ExaminationReportSerializer,
    FollowUpSerializer,
    HealthExamReportSerializer,
    MedicineBoxSerializer,
    MedicationPlanSerializer,
    MedicationRecordSerializer,
    MedExamDetailSerializer,
    MedicalCaseSerializer,
    MemberBindingUpdateSerializer,
    MemberSerializer,
    MemberMedicalProfileSerializer,
    MemberModuleSettingSerializer,
    PrescriptionSerializer,
    SurgerySerializer,
    SymptomSerializer,
    VisitSerializer,
    serialize_member_detail,
    serialize_member_list_item,
)
from medical.services import member_binding_service as binding_service
from medical.services import member_invite_service as invite_service
from medical.services.member_invite_service import InviteError
from medical.services.member_invite_delivery import create_invite_and_notify, DeliveryResult
from medical.services import member_share_ticket as share_ticket_service
from medical.services.medicine_cabinet_service import family_medicine_cabinet_queryset
from medical.services.medication_record_query import (
    apply_medication_record_scheduled_range,
    parse_medication_record_scheduled_range,
)
from medical.services.medication_plan_notification_hooks import (
    schedule_medication_plan_health_notification,
)
from medical.services.medication_reminder_authorization_service import (
    disable_local_authorization,
    load_authorization_context,
    serialize_authorization_context,
    upsert_local_authorization,
)
from medical.services.medication_reminder_service import (
    build_enabled_plans_response,
    build_member_notification_ownership,
    resolve_window_dates,
)
from file_manager.business_relations import bind_file_to_business, bind_files_to_business, files_for_business, relation_fingerprint
from file_manager.models import ManagedFile
from file_manager.serializers import ManagedFileAttachmentOutSerializer

logger = logging.getLogger("medical.flow")


class WrappedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    etag_max_age = 120

    def get_queryset(self):
        queryset = self.queryset.filter(is_deleted=False)
        model = queryset.model
        if any(field.name == "member" for field in model._meta.fields):
            return MemberPermissionGate.filter_qs(queryset, self.request.user)
        return queryset.filter(user=self.request.user)

    def _ensure_member_create_access(self, member_id: int) -> None:
        try:
            MemberPermissionGate.require_create(user=self.request.user, member_id=member_id)
        except PermissionError as exc:
            raise PermissionDenied(detail=str(exc)) from exc

    def _ensure_member_edit_access(self, member_id: int) -> None:
        try:
            MemberPermissionGate.require_edit(user=self.request.user, member_id=member_id)
        except PermissionError as exc:
            raise PermissionDenied(detail=str(exc)) from exc

    def _ensure_member_delete_access(self, member_id: int) -> None:
        try:
            MemberPermissionGate.require_delete(user=self.request.user, member_id=member_id)
        except PermissionError as exc:
            raise PermissionDenied(detail=str(exc)) from exc

    def perform_create(self, serializer):
        member = serializer.validated_data.get("member")
        if member is not None:
            self._ensure_member_create_access(member.id)
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        member = serializer.validated_data.get("member") or getattr(serializer.instance, "member", None)
        if member is not None:
            self._ensure_member_edit_access(member.id)
        serializer.save()

    def perform_destroy(self, instance):
        member = getattr(instance, "member", None)
        if member is not None:
            self._ensure_member_delete_access(member.id)
        instance.soft_delete()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        etag = self._build_collection_etag(queryset)
        if self._is_not_modified(request, etag):
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            return response

        serializer = self.get_serializer(queryset, many=True)
        response = success_response(serializer.data, msg="success", code=0, status_code=status.HTTP_200_OK)
        self._set_cache_headers(response, etag)
        return response

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        etag = self._build_object_etag(instance)
        if self._is_not_modified(request, etag):
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            return response

        serializer = self.get_serializer(instance)
        response = success_response(serializer.data, msg="success", code=0, status_code=status.HTTP_200_OK)
        self._set_cache_headers(response, etag)
        return response

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return success_response(serializer.data, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response({"id": instance.id}, msg="deleted", code=0, status_code=status.HTTP_200_OK)

    def _build_collection_etag(self, queryset):
        records = list(queryset.values_list("id", "updated_at"))
        payload = {
            "path": self.request.path,
            "query": self.request.query_params.dict(),
            "user_id": self.request.user.id,
            "records": records,
        }
        return build_etag(payload)

    def _build_object_etag(self, instance):
        payload = {"id": instance.id, "updated_at": instance.updated_at, "user_id": self.request.user.id}
        return build_etag(payload)

    def _is_not_modified(self, request, etag):
        incoming = normalize_etag(request.headers.get("If-None-Match"))
        if incoming == "":
            return False
        return incoming == normalize_etag(etag)

    def _set_cache_headers(self, response, etag):
        response["ETag"] = etag
        response["Cache-Control"] = f"private, max-age={self.etag_max_age}"


class MemberViewSet(WrappedModelViewSet):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer

    def get_queryset(self):
        return binding_service.accessible_members_queryset(self.request.user)

    def _binding_for(self, member: Member) -> UserMemberBinding:
        binding = binding_service.get_active_binding(user=self.request.user, member_id=member.id)
        if binding is None:
            raise PermissionDenied(detail="permission_denied")
        return binding

    def list(self, request, *args, **kwargs):
        members = list(self.filter_queryset(self.get_queryset()))
        bindings = {
            item.member_id: item
            for item in binding_service.active_bindings_qs()
            .filter(user=request.user, member_id__in=[m.id for m in members])
            .select_related("member")
        }
        payload = [serialize_member_list_item(member, bindings[member.id]) for member in members if member.id in bindings]
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        member = self.get_object()
        binding = self._binding_for(member)
        include_shared = binding.role in (
            UserMemberBinding.Role.OWNER,
            UserMemberBinding.Role.ADMIN,
        )
        payload = serialize_member_detail(
            member,
            binding,
            viewer=request.user,
            include_shared_users=include_shared,
        )
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = serializer.save(user=request.user)
        binding = binding_service.get_active_binding(user=request.user, member_id=member.id)
        payload = serialize_member_list_item(member, binding)
        return success_response(payload, msg="created", code=0, status_code=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        member = self.get_object()
        binding = self._binding_for(member)
        caps = binding_service.compute_capabilities(binding)
        if not caps.can_edit:
            raise PermissionDenied(detail="permission_denied")
        serializer = self.get_serializer(member, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        member = serializer.save()
        binding = self._binding_for(member)
        payload = serialize_member_list_item(member, binding)
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        member = self.get_object()
        binding = self._binding_for(member)
        caps = binding_service.compute_capabilities(binding)
        shared_count = binding_service.count_active_bindings(member.id)
        if shared_count > 1 or not caps.can_delete:
            binding_service.revoke_binding(binding)
            return success_response(
                {"id": member.id, "action": "unbound", "binding_id": binding.id},
                msg="unbound",
                code=0,
                status_code=status.HTTP_200_OK,
            )
        binding_service.delete_member_profile(member)
        return success_response(
            {"id": member.id, "action": "deleted"},
            msg="deleted",
            code=0,
            status_code=status.HTTP_200_OK,
        )


class MemberMedicalProfileViewSet(WrappedModelViewSet):
    queryset = MemberMedicalProfile.objects.all()
    serializer_class = MemberMedicalProfileSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset


class MemberModuleSettingViewSet(WrappedModelViewSet):
    queryset = MemberModuleSetting.objects.all()
    serializer_class = MemberModuleSettingSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        module_code = self.request.query_params.get("module_code")
        if module_code:
            queryset = queryset.filter(module_code=module_code)
        return queryset


class MemberBindingViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def partial_update(self, request, pk=None):
        try:
            binding = binding_service.active_bindings_qs().get(pk=pk, user=request.user)
        except UserMemberBinding.DoesNotExist:
            return error_response(msg="binding_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        serializer = MemberBindingUpdateSerializer(binding, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        member = binding.member
        payload = serialize_member_list_item(member, binding)
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        try:
            binding = binding_service.active_bindings_qs().get(pk=pk, user=request.user)
        except UserMemberBinding.DoesNotExist:
            return error_response(msg="binding_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        binding_service.revoke_binding(binding)
        return success_response({"binding_id": binding.id}, msg="unbound", code=0, status_code=status.HTTP_200_OK)


class MemberShareTicketCreateAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, member_id: int):
        from medical.services.member_permission_levels import resolve_share_role_from_request

        channel = (request.data or {}).get("channel") or "qr"
        role = resolve_share_role_from_request(request.data or {})
        try:
            MemberPermissionGate.require_share(user=request.user, member_id=member_id)
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)

        nonce = binding_service.new_share_nonce()
        payload = share_ticket_service.build_ticket_payload(
            member_id=member_id,
            inviter_user_id=request.user.id,
            role=role,
            channel=channel,
            nonce=nonce,
        )
        ticket = share_ticket_service.sign_ticket(payload)
        qr_payload = f"spark://member-share?ticket={ticket}"
        return success_response(
            {
                "share_ticket": ticket,
                "qr_payload": qr_payload,
                "nearby_payload": {
                    "type": "member_share",
                    "ticket": ticket,
                    "member_id": member_id,
                },
            },
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )


class MemberShareTicketResolveAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ticket = (request.data or {}).get("share_ticket") or ""
        if not ticket:
            return error_response(msg="share_ticket_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        try:
            resolved = share_ticket_service.resolve_ticket(ticket=ticket, acceptor=request.user)
        except ValueError as exc:
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        member = resolved["member"]
        return success_response(
            {
                "member": {
                    "id": member.id,
                    "name": member.name,
                    "gender": member.gender,
                    "birth_date": member.birth_date,
                    "avatar_url": member.avatar_url,
                },
                "inviter": {
                    "user_id": resolved["inviter"].id,
                    "display_name": resolved["inviter_display_name"],
                    "relationship": resolved["inviter_relationship"],
                },
                "default_role": resolved["role"],
                "already_bound": resolved["already_bound"],
                "existing_binding_id": resolved["existing_binding_id"],
                "shared_user_count": resolved["shared_user_count"],
            },
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )


class MemberShareTicketAcceptAPI(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data or {}
        ticket = data.get("share_ticket") or ""
        relationship = (data.get("relationship") or "").strip()
        custom_relationship = (data.get("custom_relationship") or "").strip()
        if not ticket:
            return error_response(msg="share_ticket_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        if not relationship:
            return error_response(msg="relationship_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        try:
            payload = share_ticket_service.unsign_ticket(ticket)
            resolved = share_ticket_service.resolve_ticket(ticket=ticket, acceptor=request.user)
        except signing.BadSignature:
            return error_response(msg="share_ticket_invalid", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        member = resolved["member"]
        inviter = resolved["inviter"]
        binding, _created = binding_service.accept_share_binding(
            user=request.user,
            member=member,
            relationship=relationship,
            custom_relationship=custom_relationship,
            role=payload.get("role") or UserMemberBinding.Role.VIEWER,
            invited_by=inviter,
        )
        item = serialize_member_list_item(member, binding)
        return success_response(item, msg="accepted", code=0, status_code=status.HTTP_200_OK)


def _invite_member_summary(member: Member) -> dict:
    return {
        "id": member.id,
        "name": member.name,
        "gender": member.gender,
        "birth_date": member.birth_date,
        "avatar_url": member.avatar_url,
    }


def _invite_inviter_summary(inviter: User, member_id: int) -> dict:
    binding = binding_service.get_active_binding(user=inviter, member_id=member_id)
    relationship = binding.relationship if binding else "self"
    return {
        "user_id": inviter.id,
        "display_name": binding_service._masked_user_label(inviter),
        "relationship": relationship,
    }


def _serialize_pending_invite(invite: MemberShareInvite) -> dict:
    from medical.services.member_permission_levels import role_to_permission

    return {
        "invite_id": invite.id,
        "member": _invite_member_summary(invite.member),
        "inviter": _invite_inviter_summary(invite.inviter_user, invite.member_id),
        "role": invite.role,
        "permission": role_to_permission(invite.role),
        "channel": invite.channel,
        "expires_at": invite.expires_at,
    }


class MemberShareInviteCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, member_id: int):
        data = request.data or {}
        # Accept both field name styles (camelCase from Swift client and snake_case)
        channel = (data.get("channel") or data.get("target_type") or "").strip().lower()
        contact = (
            data.get("target_contact")
            or data.get("targetContact")
            or data.get("target")
            or ""
        ).strip()
        from common.exceptions import APIError
        from medical.services.member_permission_levels import resolve_share_role_from_request

        role = resolve_share_role_from_request(data)
        country_code = (data.get("country_code") or data.get("countryCode") or "+86").strip()
        phone_raw = (data.get("phone") or contact).strip() if channel == MemberShareInvite.Channel.PHONE else contact

        if channel not in (
            MemberShareInvite.Channel.PHONE,
            MemberShareInvite.Channel.EMAIL,
            MemberShareInvite.Channel.IN_APP,
        ):
            return error_response(msg="invalid_channel", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        if not contact and not phone_raw:
            return error_response(msg="target_contact_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        try:
            member = Member.objects.get(pk=member_id, is_deleted=False)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        from accounts.services.device_session_service import DeviceSessionService

        claims = (
            DeviceSessionService._claims_from_validated_token(request.auth)
            if request.auth is not None
            else {}
        )
        bundle_id = (claims.get("bundle_id") or "").strip()

        normalized_contact = ""
        lookup_contact = phone_raw if channel == MemberShareInvite.Channel.PHONE else contact
        try:
            target_user, normalized_contact = invite_service.resolve_user_by_contact(
                channel=channel,
                contact=lookup_contact,
                country_code=country_code,
                bundle_id=bundle_id,
            )
        except APIError:
            return error_response(msg="phone_invalid", code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        # Cannot invite if user is already bound
        if target_user is not None and binding_service.get_active_binding(user=target_user, member_id=member_id):
            return error_response(msg="already_bound", code=-1, status_code=status.HTTP_409_CONFLICT)

        try:
            invite, delivery = create_invite_and_notify(
                member=member,
                inviter=request.user,
                target_user=target_user,
                channel=channel,
                role=role,
                target_contact=normalized_contact or contact,
            )
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        except InviteError as exc:
            msg = str(exc)
            http_status = status.HTTP_400_BAD_REQUEST
            if msg == "already_bound":
                http_status = status.HTTP_409_CONFLICT
            return error_response(msg=msg, code=-1, status_code=http_status)

        open_url = f"spark://member-invite?id={invite.id}"
        from medical.services.member_permission_levels import role_to_permission

        response_data = {
            "invite_id": invite.id,
            "member_id": member_id,
            "status": invite.status,
            "expires_at": invite.expires_at,
            "permission": role_to_permission(invite.role),
            "matched_user_id": target_user.id if target_user else None,
            **delivery.to_dict(),
        }
        if channel == MemberShareInvite.Channel.PHONE and normalized_contact:
            response_data["normalized_phone"] = normalized_contact
        return success_response(
            response_data,
            msg=delivery.api_msg(),
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class PendingMemberInvitesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        invites = invite_service.pending_invites_for_user(request.user)
        payload = [_serialize_pending_invite(item) for item in invites]
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)


class MemberShareInviteDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, invite_id: int):
        try:
            invite = (
                MemberShareInvite.objects.select_related("member", "inviter_user")
                .get(pk=invite_id)
            )
        except MemberShareInvite.DoesNotExist:
            return error_response(msg="invite_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        # Only inviter or target_user may see the detail
        if invite.inviter_user_id != request.user.id and invite.target_user_id != request.user.id:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)

        return success_response(
            _serialize_pending_invite(invite),
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )


class MemberShareInviteAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, invite_id: int):
        data = request.data or {}
        relationship = (data.get("relationship") or "").strip()
        custom_relationship = (data.get("custom_relationship") or data.get("customRelationship") or "").strip()
        if not relationship:
            return error_response(msg="relationship_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        try:
            invite = MemberShareInvite.objects.select_related("member").get(pk=invite_id)
        except MemberShareInvite.DoesNotExist:
            return error_response(msg="invite_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        try:
            binding = invite_service.accept_invite(
                invite=invite,
                acceptor=request.user,
                relationship=relationship,
                custom_relationship=custom_relationship,
            )
        except InviteError as exc:
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        item = serialize_member_list_item(invite.member, binding)
        return success_response(item, msg="accepted", code=0, status_code=status.HTTP_200_OK)


class MemberShareInviteRejectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, invite_id: int):
        try:
            invite = MemberShareInvite.objects.get(pk=invite_id)
        except MemberShareInvite.DoesNotExist:
            return error_response(msg="invite_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        try:
            invite_service.reject_invite(invite=invite, user=request.user)
        except InviteError as exc:
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        return success_response({"invite_id": invite.id, "status": invite.status}, msg="rejected", code=0)


class MemberShareInviteCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, invite_id: int):
        try:
            invite = MemberShareInvite.objects.get(pk=invite_id)
        except MemberShareInvite.DoesNotExist:
            return error_response(msg="invite_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        try:
            invite_service.cancel_invite(invite=invite, inviter=request.user)
        except InviteError as exc:
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        return success_response({"invite_id": invite.id, "status": invite.status}, msg="cancelled", code=0)


class MemberBindingRoleUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk: int):
        role = (request.data or {}).get("role") or ""
        try:
            binding = binding_service.active_bindings_qs().select_related("member").get(pk=pk)
        except UserMemberBinding.DoesNotExist:
            return error_response(msg="binding_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        try:
            MemberPermissionGate.require_manage(user=request.user, member_id=binding.member_id)
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        try:
            binding = binding_service.change_binding_role(binding, role)
        except ValueError as exc:
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        viewer_binding = binding_service.get_active_binding(user=request.user, member_id=binding.member_id)
        payload = serialize_member_list_item(binding.member, viewer_binding)
        return success_response(payload, msg="updated", code=0, status_code=status.HTTP_200_OK)


class MemberBindingPermissionUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk: int):
        from medical.services.member_permission_levels import role_to_permission
        from medical.services.member_permission_service import MemberPermissionDenied

        permission = ((request.data or {}).get("permission") or "").strip().lower()
        if not permission:
            return error_response(msg="permission_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        try:
            binding = binding_service.active_bindings_qs().select_related("member").get(pk=pk)
        except UserMemberBinding.DoesNotExist:
            return error_response(msg="binding_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        try:
            MemberPermissionGate.require_manage(user=request.user, member_id=binding.member_id)
        except MemberPermissionDenied as exc:
            return MemberPermissionGate.permission_denied_response(exc, error_response)
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        try:
            binding = binding_service.change_binding_permission(binding, permission)
        except ValueError as exc:
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        caps = binding_service.compute_capabilities(binding)
        return success_response(
            {
                "binding_id": binding.id,
                "permission": role_to_permission(binding.role),
                "capabilities": binding_service.capabilities_to_dict(caps),
            },
            msg="updated",
            code=0,
            status_code=status.HTTP_200_OK,
        )


class MemberBindingRemoveView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk: int):
        try:
            binding = binding_service.active_bindings_qs().select_related("member").get(pk=pk)
        except UserMemberBinding.DoesNotExist:
            return error_response(msg="binding_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        try:
            MemberPermissionGate.require_remove_shared(user=request.user, member_id=binding.member_id)
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        if binding.user_id == request.user.id:
            return error_response(msg="cannot_remove_self", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        try:
            binding_service.remove_binding(binding)
        except ValueError as exc:
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        return success_response({"binding_id": binding.id}, msg="removed", code=0, status_code=status.HTTP_200_OK)


class MemberBindingTransferOwnerView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk: int):
        try:
            target_binding = binding_service.active_bindings_qs().select_related("member").get(pk=pk)
        except UserMemberBinding.DoesNotExist:
            return error_response(msg="binding_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        owner_binding = binding_service.get_active_binding(user=request.user, member_id=target_binding.member_id)
        if owner_binding is None or owner_binding.role != UserMemberBinding.Role.OWNER:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        try:
            binding_service.transfer_owner(
                current_owner_binding=owner_binding,
                target_binding=target_binding,
            )
        except ValueError as exc:
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        owner_binding.refresh_from_db()
        payload = serialize_member_list_item(target_binding.member, owner_binding)
        return success_response(payload, msg="transferred", code=0, status_code=status.HTTP_200_OK)


class MedicalCaseViewSet(WrappedModelViewSet):
    queryset = MedicalCase.objects.select_related("member").all()
    serializer_class = MedicalCaseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset


class SymptomViewSet(WrappedModelViewSet):
    queryset = Symptom.objects.select_related("member", "medical_case").all()
    serializer_class = SymptomSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        return queryset


class VisitViewSet(WrappedModelViewSet):
    queryset = Visit.objects.select_related("member", "medical_case").all()
    serializer_class = VisitSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        return queryset


class SurgeryViewSet(WrappedModelViewSet):
    queryset = Surgery.objects.select_related("member", "medical_case").all()
    serializer_class = SurgerySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        return queryset


class FollowUpViewSet(WrappedModelViewSet):
    queryset = FollowUp.objects.select_related("member", "medical_case").all()
    serializer_class = FollowUpSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        return queryset


def _attachments_payload(user, business_type: str, business_id: int):
    """complete-data 内病历等非 ModelSerializer 场景仍用手写附件列表。"""
    qs = files_for_business(user, business_type, business_id)
    return ManagedFileAttachmentOutSerializer(
        qs,
        many=True,
        context={"business_type": business_type, "business_id": str(business_id)},
    ).data


def _report_row_payload(serializer, instance):
    row = dict(serializer.to_representation(instance))
    row.pop("raw_ocr", None)
    return row


class ExaminationReportViewSet(WrappedModelViewSet):
    queryset = ExaminationReport.objects.select_related("member", "medical_record").all()
    serializer_class = ExaminationReportSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset


class HealthExamReportViewSet(WrappedModelViewSet):
    queryset = HealthExamReport.objects.select_related("member").all()
    serializer_class = HealthExamReportSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        return queryset


class MedExamDetailViewSet(WrappedModelViewSet):
    """明细表无 `user` 外键，按成员绑定过滤可访问范围（与报告列表一致）。"""

    queryset = MedExamDetail.objects.select_related("member").all()
    serializer_class = MedExamDetailSerializer

    def get_queryset(self):
        queryset = MedExamDetail.objects.select_related("member").filter(is_deleted=False)
        queryset = MemberPermissionGate.filter_qs(queryset, self.request.user)
        member_id = self.request.query_params.get("member_id")
        business_type = self.request.query_params.get("business_type")
        business_id = self.request.query_params.get("business_id")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if business_type:
            queryset = queryset.filter(business_type=business_type)
        if business_id:
            queryset = queryset.filter(business_id=business_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted", "updated_at"])


class MedicineBoxViewSet(WrappedModelViewSet):
    queryset = MedicineBox.objects.select_related("member").all()
    serializer_class = MedicineBoxSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset.filter(is_deleted=False)
        member_ids = binding_service.accessible_member_ids(user)
        if not member_ids:
            return queryset.none()
        owner_ids = Member.objects.filter(id__in=member_ids, is_deleted=False).values_list("user_id", flat=True).distinct()
        queryset = queryset.filter(Q(member_id__in=member_ids) | Q(member_id__isnull=True, user_id__in=owner_ids))
        member_id = self.request.query_params.get("member_id")
        medicine_type = self.request.query_params.get("medicine_type")
        expire_before = self.request.query_params.get("expire_before")
        low_stock = self.request.query_params.get("low_stock")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medicine_type:
            queryset = queryset.filter(medicine_type=medicine_type)
        if expire_before:
            queryset = queryset.filter(expire_date__lte=expire_before)
        if low_stock in {"1", "true", "True", "yes"}:
            queryset = queryset.filter(total_quantity__lte=0)
        return queryset

    def perform_create(self, serializer):
        member = serializer.validated_data.get("member")
        owner_user = serializer.validated_data.pop("_owner_user", None)
        entry_member_id = serializer.validated_data.pop("entry_member_id", None)
        if member is not None:
            self._ensure_member_create_access(member.id)
            owner_user = owner_user or member.user
        else:
            resolved_entry = entry_member_id
            if resolved_entry is None:
                raw = self.request.data.get("entry_member_id")
                resolved_entry = int(raw) if raw not in (None, "") else None
            self._ensure_member_create_access(resolved_entry)
            if owner_user is None:
                owner_user = Member.objects.get(pk=resolved_entry, is_deleted=False).user
        serializer.save(user=owner_user)

    def _resolve_public_medicine_entry_member_id(self, owner_user_id: int) -> int:
        accessible = binding_service.accessible_member_ids(self.request.user)
        member_id = (
            Member.objects.filter(user_id=owner_user_id, id__in=accessible, is_deleted=False)
            .values_list("id", flat=True)
            .first()
        )
        if member_id is None:
            raise PermissionDenied(detail="permission_denied")
        return member_id

    def perform_update(self, serializer):
        member = serializer.validated_data.get("member")
        if member is None and "member" not in serializer.validated_data:
            member = getattr(serializer.instance, "member", None)
        serializer.validated_data.pop("_owner_user", None)
        if member is not None:
            self._ensure_member_edit_access(member.id)
        else:
            raw = self.request.data.get("entry_member_id")
            if raw not in (None, ""):
                self._ensure_member_edit_access(int(raw))
            else:
                entry_member_id = self._resolve_public_medicine_entry_member_id(serializer.instance.user_id)
                self._ensure_member_edit_access(entry_member_id)
        serializer.save()

    def perform_destroy(self, instance):
        member = getattr(instance, "member", None)
        if member is not None:
            self._ensure_member_delete_access(member.id)
        else:
            entry_id = self._resolve_public_medicine_entry_member_id(instance.user_id)
            self._ensure_member_delete_access(entry_id)
        instance.soft_delete()


class FamilyMedicineCabinetSummaryAPI(APIView):
    """家庭药箱汇总：按入口成员 ID 返回创建者名下全部药品。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw_member_id = request.query_params.get("member_id")
        if raw_member_id in (None, ""):
            return error_response(msg="member_id_required", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        try:
            entry_member_id = int(raw_member_id)
        except (TypeError, ValueError):
            return error_response(msg="invalid_member_id", code=-1, status_code=status.HTTP_400_BAD_REQUEST)
        try:
            queryset = family_medicine_cabinet_queryset(user=request.user, entry_member_id=entry_member_id)
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        serializer = MedicineBoxSerializer(queryset, many=True, context={"request": request})
        return success_response(serializer.data, msg="success", code=0, status_code=status.HTTP_200_OK)


class PrescriptionViewSet(WrappedModelViewSet):
    queryset = Prescription.objects.select_related("member", "medical_case").all()
    serializer_class = PrescriptionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        status_value = self.request.query_params.get("status")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    def _build_collection_etag(self, queryset):
        records = list(queryset.values_list("id", "updated_at"))
        prescription_ids = [str(pid) for pid, _ in records]
        attachments = []
        if prescription_ids:
            attachments = list(
                relation_fingerprint(self.request.user, [("prescription_batch", prescription_ids)])
            )
        payload = {
            "path": self.request.path,
            "query": self.request.query_params.dict(),
            "user_id": self.request.user.id,
            "records": records,
            "attachments": attachments,
        }
        return build_etag(payload)

    def _build_object_etag(self, instance):
        attachments = relation_fingerprint(self.request.user, [("prescription_batch", [instance.id])])
        payload = {
            "id": instance.id,
            "updated_at": instance.updated_at,
            "user_id": self.request.user.id,
            "attachments": attachments,
        }
        return build_etag(payload)


class MedicationPlanViewSet(WrappedModelViewSet):
    queryset = MedicationPlan.objects.select_related("member", "medical_case", "medicine_box", "prescription").all()
    serializer_class = MedicationPlanSerializer

    def perform_create(self, serializer):
        member = serializer.validated_data.get("member")
        if member is not None:
            self._ensure_member_create_access(member.id)
        plan = serializer.save(user=self.request.user)
        schedule_medication_plan_health_notification(
            actor_user=self.request.user,
            plan=plan,
            created=True,
        )

    def perform_update(self, serializer):
        member = serializer.validated_data.get("member") or getattr(serializer.instance, "member", None)
        if member is not None:
            self._ensure_member_edit_access(member.id)
        plan = serializer.save()
        schedule_medication_plan_health_notification(
            actor_user=self.request.user,
            plan=plan,
            created=False,
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        medical_case_id = self.request.query_params.get("medical_case_id")
        medicine_box_id = self.request.query_params.get("medicine_box_id")
        prescription_id = self.request.query_params.get("prescription_id")
        status_value = self.request.query_params.get("status")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if medical_case_id:
            queryset = queryset.filter(medical_case_id=medical_case_id)
        if medicine_box_id:
            queryset = queryset.filter(medicine_box_id=medicine_box_id)
        if prescription_id:
            queryset = queryset.filter(prescription_id=prescription_id)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    def _build_collection_etag(self, queryset):
        records = list(queryset.values_list("id", "updated_at"))
        plan_ids = [str(plan_id) for plan_id, _ in records]
        attachments = []
        if plan_ids:
            attachments = list(
                relation_fingerprint(self.request.user, [("medication_plan", plan_ids)])
            )
        payload = {
            "path": self.request.path,
            "query": self.request.query_params.dict(),
            "user_id": self.request.user.id,
            "records": records,
            "attachments": attachments,
        }
        return build_etag(payload)

    def _build_object_etag(self, instance):
        attachments = relation_fingerprint(self.request.user, [("medication_plan", [instance.id])])
        payload = {
            "id": instance.id,
            "updated_at": instance.updated_at,
            "user_id": self.request.user.id,
            "attachments": attachments,
        }
        return build_etag(payload)


class MedicationRecordViewSet(WrappedModelViewSet):
    queryset = MedicationRecord.objects.select_related("member", "plan", "plan__medicine_box").all()
    serializer_class = MedicationRecordSerializer

    def list(self, request, *args, **kwargs):
        _, range_error = parse_medication_record_scheduled_range(request.query_params)
        if range_error is not None:
            return range_error
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        member_id = self.request.query_params.get("member_id")
        plan_id = self.request.query_params.get("plan_id")
        status_value = self.request.query_params.get("status")
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if plan_id:
            queryset = queryset.filter(plan_id=plan_id)
        if status_value:
            queryset = queryset.filter(status=status_value)

        scheduled_range, _ = parse_medication_record_scheduled_range(self.request.query_params)
        return apply_medication_record_scheduled_range(queryset, scheduled_range)

    def perform_update(self, serializer):
        with transaction.atomic():
            locked = (
                MedicationRecord.objects.select_for_update()
                .select_related("plan", "plan__medicine_box")
                .get(pk=serializer.instance.pk, user=self.request.user, is_deleted=False)
            )
            previous_status = locked.status
            serializer.instance = locked
            obj = serializer.save()
            if previous_status != MedicationRecord.Status.TAKEN and obj.status == MedicationRecord.Status.TAKEN:
                self._consume_inventory(obj)
                ModelChangeLog.objects.create(
                    user=self.request.user,
                    member=obj.member,
                    entity="medication_record",
                    entity_id=obj.id,
                    action="taken",
                    from_status=previous_status,
                    to_status=obj.status,
                    changed_fields={"inventory_consumed": True},
                    trace_id=self.request.headers.get("X-Request-ID", ""),
                    operator=str(self.request.user.id),
                )

    def _consume_inventory(self, record):
        plan = record.plan
        if plan.medicine_box_id is None or plan.dose_value is None:
            return
        box = MedicineBox.objects.select_for_update().get(pk=plan.medicine_box_id, user=record.user, is_deleted=False)
        if box.total_quantity is None:
            return
        consumed = plan.dose_value
        next_total = box.total_quantity - consumed
        if next_total < 0:
            next_total = 0
        box.total_quantity = next_total
        box.save(update_fields=["total_quantity", "updated_at"])


class MedicationReminderEnabledPlansAPI(APIView):
    """开启提醒用药计划聚合：仅服务客户端本地通知补全，不是通用用药计划列表。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import date as date_cls

        raw_start = request.query_params.get("window_start_date")
        raw_end = request.query_params.get("window_end_date")
        include_records = request.query_params.get("include_records", "true").lower() != "false"

        start_date = None
        end_date = None
        try:
            if raw_start:
                start_date = date_cls.fromisoformat(raw_start[:10])
            if raw_end:
                end_date = date_cls.fromisoformat(raw_end[:10])
        except ValueError:
            return error_response(
                msg="invalid_window_date",
                code=-1,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        window = resolve_window_dates(window_start_date=start_date, window_end_date=end_date)
        data = build_enabled_plans_response(
            user=request.user,
            window=window,
            include_records=include_records,
            request=request,
        )
        logger.info(
            "enabled-plans user_id=%s members=%s",
            request.user.id,
            len(data.get("members") or []),
        )
        return success_response(data, msg="success", code=0, status_code=status.HTTP_200_OK)


class MemberNotificationOwnershipAPI(APIView):
    """成员通知归属：relationship=self 表示健康资料本人，与 role=owner/admin 管理权限不同。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, member_id: int):
        data = build_member_notification_ownership(user=request.user, member_id=member_id)
        if data is None:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        logger.info(
            "notification-ownership user_id=%s member_id=%s has_other_self_owner=%s",
            request.user.id,
            member_id,
            data.get("has_other_self_owner"),
        )
        return success_response(data, msg="success", code=0, status_code=status.HTTP_200_OK)

class MedicationReminderLocalAuthorizationAPI(APIView):
    """
    服药计划本机本地提醒授权接口
    业务说明：控制当前登录用户是否有权限，为他人的服药计划在本机推送系统服药通知
    支持查询授权状态、开启/关闭授权、彻底取消授权三条接口
    """

    # 权限校验：仅登录用户可访问
    permission_classes = [IsAuthenticated]

    def get(self, request, plan_id: int):
        """
        GET 请求：查询指定服药计划的本机提醒授权信息
        :param request: 请求对象，携带登录用户信息
        :param plan_id: 目标服药计划ID
        :return: 成功：返回授权序列化数据；失败：404计划不存在 / 403无访问权限
        """
        try:
            # 加载当前用户与目标计划的授权上下文（校验计划归属、用户访问权限）
            context = load_authorization_context(user=request.user, plan_id=plan_id)
        except MedicationPlan.DoesNotExist:
            # 数据库无对应服药计划
            return error_response(msg="medication_plan_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        except PermissionError:
            # 用户无权查看该服药计划
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)

        # 将授权上下文转为前端可识别JSON数据
        data = serialize_authorization_context(user=request.user, context=context)
        return success_response(data, msg="success", code=0, status_code=status.HTTP_200_OK)

    def put(self, request, plan_id: int):
        """
        PUT 请求：新增/更新本机提醒授权状态
        请求体参数：
            enabled: bool 是否开启本机通知，默认True
            source: str 操作来源页面/模块标记，用于日志追溯
        :param request: 请求对象
        :param plan_id: 目标服药计划ID
        :return: 成功：返回更新后的授权数据；失败：404计划不存在 / 403无权限 / 400参数非法
        """
        # 读取前端传入开关状态，缺失则默认开启提醒
        enabled = bool(request.data.get("enabled", True))
        # 读取操作来源标识，空值统一转为空字符串
        source = str(request.data.get("source") or "").strip()
        try:
            # 新增或更新本地授权记录
            data = upsert_local_authorization(
                user=request.user,
                plan_id=plan_id,
                enabled=enabled,
                source=source,
            )
        except MedicationPlan.DoesNotExist:
            return error_response(msg="medication_plan_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            # 参数校验失败，返回具体错误文案
            return error_response(msg=str(exc), code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        # 记录更新授权操作日志：用户ID、计划ID、开关状态、记录是否已存在
        logger.info(
            "local-authorization put user_id=%s plan_id=%s enabled=%s exists=%s",
            request.user.id,
            plan_id,
            data.get("enabled"),
            data.get("exists"),
        )
        return success_response(data, msg="success", code=0, status_code=status.HTTP_200_OK)

    def delete(self, request, plan_id: int):
        """
        DELETE 请求：永久关闭/删除本机提醒授权记录
        :param request: 请求对象
        :param plan_id: 目标服药计划ID
        :return: 成功：返回处理后授权数据；失败：404计划不存在 / 403无权限
        """
        try:
            # 清除当前用户对该计划的本地通知授权
            data = disable_local_authorization(user=request.user, plan_id=plan_id)
        except MedicationPlan.DoesNotExist:
            return error_response(msg="medication_plan_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)

        # 记录删除授权操作日志
        logger.info(
            "local-authorization delete user_id=%s plan_id=%s enabled=%s exists=%s",
            request.user.id,
            plan_id,
            data.get("enabled"),
            data.get("exists"),
        )
        return success_response(data, msg="success", code=0, status_code=status.HTTP_200_OK)


class MemberCompleteDataAPI(APIView):
    """成员医疗数据汇总（单接口）：病例汇总、症状/就诊/手术/随访、体检/检查报告头、处方批次与附件；不含检验/体检明细行。"""

    permission_classes = [IsAuthenticated]
    etag_max_age = 86400

    def get(self, request, member_id: int):
        try:
            binding = MemberPermissionGate.require_access(user=request.user, member_id=member_id)
            member = binding.member
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        medical_cases = (
            MedicalCase.objects.filter(is_deleted=False, member_id=member_id)
            .prefetch_related(
                "symptoms",
                "prescriptions__plans",
                "medication_plans",
            )
            .order_by("-created_at")
        )

        health_exam_reports = HealthExamReport.objects.filter(
            is_deleted=False,
            member_id=member_id,
        ).order_by("-exam_date", "-updated_at")

        examination_reports = ExaminationReport.objects.select_related("medical_record").filter(
            is_deleted=False,
            member_id=member_id,
        ).order_by("-performed_at", "-updated_at")

        medicine_boxes = MedicineBox.objects.filter(
            is_deleted=False,
            member_id=member_id,
        ).order_by("-updated_at", "-id")

        prescriptions = Prescription.objects.filter(
            is_deleted=False,
            member_id=member_id,
        ).order_by("-prescribed_at", "-updated_at", "-id")

        medication_plans = MedicationPlan.objects.select_related(
            "medicine_box",
            "prescription",
        ).filter(
            is_deleted=False,
            member_id=member_id,
        ).order_by("-start_date", "-updated_at", "-id")

        today = timezone.localdate()
        today_medication_records = MedicationRecord.objects.select_related("plan").filter(
            is_deleted=False,
            member_id=member_id,
            scheduled_at__date=today,
        ).order_by("scheduled_at", "dose_sequence", "id")

        symptoms = Symptom.objects.filter(is_deleted=False, member_id=member_id).order_by(
            "-created_at", "-updated_at", "-id"
        )
        visits = Visit.objects.filter(is_deleted=False, member_id=member_id).order_by(
            "-visited_at", "-updated_at", "-id"
        )
        surgeries = Surgery.objects.filter(is_deleted=False, member_id=member_id).order_by(
            "-performed_at", "-updated_at", "-id"
        )
        follow_ups = FollowUp.objects.filter(is_deleted=False, member_id=member_id).order_by(
            "-completed_at", "-updated_at", "-id"
        )

        etag = self._build_complete_etag(
            request=request,
            member=member,
            medical_cases=medical_cases,
            health_exam_reports=health_exam_reports,
            examination_reports=examination_reports,
            medicine_boxes=medicine_boxes,
            prescriptions=prescriptions,
            medication_plans=medication_plans,
            today_medication_records=today_medication_records,
            symptoms=symptoms,
            visits=visits,
            surgeries=surgeries,
            follow_ups=follow_ups,
        )
        if self._is_not_modified(request, etag):
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            self._set_cache_headers(response, etag)
            return response

        def attachments_payload(business_type: str, business_id: int):
            qs = files_for_business(request.user, business_type, business_id)
            return ManagedFileAttachmentOutSerializer(
                qs,
                many=True,
                context={"business_type": business_type, "business_id": str(business_id)},
            ).data

        medical_cases_payload = []
        for c in medical_cases:
            symptom_names = [s.name for s in c.symptoms.all()]
            drug_names = []
            for prescription in c.prescriptions.all():
                for plan in prescription.plans.all():
                    dn = (plan.drug_name or "").strip()
                    if dn and dn not in drug_names:
                        drug_names.append(dn)
            for plan in c.medication_plans.all():
                dn = (plan.drug_name or "").strip()
                if dn and dn not in drug_names:
                    drug_names.append(dn)
            medical_cases_payload.append(
                {
                    "id": c.id,
                    "member": c.member_id,
                    "record_type": c.record_type,
                    "status": c.status,
                    "title": c.title,
                    "hospital_name": c.hospital_name,
                    "age_at_visit": c.age_at_visit,
                    "diagnosis_summary": c.diagnosis_summary,
                    "extra": c.extra,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                    "symptoms": symptom_names,
                    "medications": drug_names,
                    "attachments": attachments_payload("medical_case", c.id),
                }
            )

        report_serializer_context = {"request": request}
        health_payload = [
            _report_row_payload(
                HealthExamReportSerializer(h, context=report_serializer_context),
                h,
            )
            for h in health_exam_reports
        ]

        exam_payload = [
            _report_row_payload(
                ExaminationReportSerializer(e, context=report_serializer_context),
                e,
            )
            for e in examination_reports
        ]

        medicine_box_payload = MedicineBoxSerializer(medicine_boxes, many=True, context={"request": request}).data
        prescription_payload = PrescriptionSerializer(prescriptions, many=True, context={"request": request}).data
        medication_plan_payload = MedicationPlanSerializer(
            medication_plans,
            many=True,
            context={"request": request},
        ).data
        today_medication_record_payload = MedicationRecordSerializer(today_medication_records, many=True).data

        today_total = today_medication_records.count()
        today_taken = today_medication_records.filter(status=MedicationRecord.Status.TAKEN).count()
        today_skipped = today_medication_records.filter(status=MedicationRecord.Status.SKIPPED).count()
        active_plan_count = medication_plans.filter(status=MedicationPlan.Status.ACTIVE).count()
        low_stock_count = medicine_boxes.filter(total_quantity__lte=0).count()
        expiring_before = today + timedelta(days=30)
        expiring_soon_count = medicine_boxes.filter(expire_date__isnull=False, expire_date__lte=expiring_before).count()
        adherence_rate = round((today_taken / today_total) * 100, 2) if today_total else 0

        symptoms_payload = SymptomSerializer(symptoms, many=True).data
        visits_payload = VisitSerializer(visits, many=True).data
        surgeries_payload = SurgerySerializer(surgeries, many=True).data
        follow_ups_payload = FollowUpSerializer(follow_ups, many=True).data

        member_data = MemberSerializer(member, context={"request": request}).data
        member_data["relationship"] = binding.relationship

        payload = {
            "member_id": member_id,
            "member": member_data,
            "medical_cases": medical_cases_payload,
            "health_exam_reports": health_payload,
            "examination_reports": exam_payload,
            "medicine_boxes": medicine_box_payload,
            "prescriptions": prescription_payload,
            "medication_plans": medication_plan_payload,
            "today_medication_records": today_medication_record_payload,
            "medication_summary": {
                "today_total": today_total,
                "today_taken": today_taken,
                "today_skipped": today_skipped,
                "adherence_rate": adherence_rate,
                "active_plan_count": active_plan_count,
                "low_stock_count": low_stock_count,
                "expiring_soon_count": expiring_soon_count,
            },
            "symptoms": symptoms_payload,
            "visits": visits_payload,
            "surgeries": surgeries_payload,
            "follow_ups": follow_ups_payload,
        }
        response = success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
        self._set_cache_headers(response, etag)
        return response

    def _build_complete_etag(
        self,
        request,
        member,
        medical_cases,
        health_exam_reports,
        examination_reports,
        medicine_boxes,
        prescriptions,
        medication_plans,
        today_medication_records,
        symptoms,
        visits,
        surgeries,
        follow_ups,
    ):
        case_ids = [str(pk) for pk in medical_cases.values_list("id", flat=True)]
        hex_ids = [str(pk) for pk in health_exam_reports.values_list("id", flat=True)]
        er_ids = [str(pk) for pk in examination_reports.values_list("id", flat=True)]
        medicine_box_ids = [str(pk) for pk in medicine_boxes.values_list("id", flat=True)]
        prescription_ids = [str(pk) for pk in prescriptions.values_list("id", flat=True)]
        medication_plan_ids = [str(pk) for pk in medication_plans.values_list("id", flat=True)]

        relation_specs = []
        if case_ids:
            relation_specs.append(("medical_case", case_ids))
        if hex_ids:
            relation_specs.append(("health_exam_report", hex_ids))
        if er_ids:
            relation_specs.append(("examination_report", er_ids))
        if medicine_box_ids:
            relation_specs.append(("medicine_box", medicine_box_ids))
        if prescription_ids:
            relation_specs.append(("prescription_batch", prescription_ids))
        if medication_plan_ids:
            relation_specs.append(("medication_plan", medication_plan_ids))

        attachments_fingerprint = relation_fingerprint(request.user, relation_specs)

        payload = {
            "path": request.path,
            "user_id": request.user.id,
            "member": (member.id, member.updated_at),
            "collections": {
                "medical_cases": list(medical_cases.values_list("id", "updated_at")),
                "health_exam_reports": list(health_exam_reports.values_list("id", "updated_at")),
                "examination_reports": list(examination_reports.values_list("id", "updated_at")),
                "medicine_boxes": list(medicine_boxes.values_list("id", "updated_at")),
                "prescriptions": list(prescriptions.values_list("id", "updated_at")),
                "medication_plans": list(medication_plans.values_list("id", "updated_at")),
                "today_medication_records": list(today_medication_records.values_list("id", "updated_at")),
                "symptoms": list(symptoms.values_list("id", "updated_at")),
                "visits": list(visits.values_list("id", "updated_at")),
                "surgeries": list(surgeries.values_list("id", "updated_at")),
                "follow_ups": list(follow_ups.values_list("id", "updated_at")),
                "attachments": attachments_fingerprint,
            },
        }
        return build_etag(payload)

    def _is_not_modified(self, request, etag):
        incoming = normalize_etag(request.headers.get("If-None-Match"))
        if incoming == "":
            return False
        return incoming == normalize_etag(etag)

    def _set_cache_headers(self, response, etag):
        response["ETag"] = etag
        response["Cache-Control"] = f"private, max-age={self.etag_max_age}"


class _WorkflowBaseAPIView(APIView):
    permission_classes = [IsAuthenticated]
    _NULLISH_DATETIME_TOKENS = {"", "无", "未提及", "未知", "none", "null", "n/a", "na", "-", "--"}

    def _bind_files(self, user, business_type, business_id, file_ids):
        return bind_files_to_business(user, business_type, business_id, file_ids)

    @staticmethod
    def _pop_file_ids(payload, *keys):
        if not hasattr(payload, "pop"):
            return []
        file_ids = []
        for key in keys or ("file_ids", "source_file_ids"):
            value = payload.pop(key, [])
            if isinstance(value, list):
                file_ids.extend(value)
        return list(dict.fromkeys(file_ids))

    def _validate_or_error(self, serializer):
        if serializer.is_valid():
            return None
        # 保留字段级结构，客户端可读化后统一拼接本地化前缀。
        return error_response(msg=serializer.errors, code=-1, status_code=status.HTTP_400_BAD_REQUEST)

    @classmethod
    def _normalize_nullable_datetime(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed.lower() in cls._NULLISH_DATETIME_TOKENS or trimmed in cls._NULLISH_DATETIME_TOKENS:
                return None
            return trimmed
        return value

    def _resolve_member_and_case(self, request, payload, default_case_title: str):
        member_id = payload.get("member")
        if not member_id:
            return None, None, error_response(
                msg={"member": [_("member is required")]},
                code=-1,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            binding = MemberPermissionGate.require_write(user=request.user, member_id=member_id)
        except PermissionError:
            return None, None, error_response(
                msg="permission_denied",
                code=-1,
                status_code=status.HTTP_403_FORBIDDEN,
            )
        member = binding.member

        medical_case_id = payload.get("medical_case")
        if medical_case_id:
            try:
                medical_case = MedicalCase.objects.get(
                    id=medical_case_id,
                    is_deleted=False,
                    member_id=member.id,
                )
            except MedicalCase.DoesNotExist:
                return None, None, error_response(
                    msg={"medical_case": [_("invalid medical_case")]},
                    code=-1,
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if medical_case.member_id != member.id:
                return None, None, error_response(
                    msg={"medical_case": [_("medical_case does not belong to member")]},
                    code=-1,
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            return member, medical_case, None

        # 兼容客户端传 medical_case = null：自动创建占位病例。
        medical_case = MedicalCase.objects.create(
            user=request.user,
            member=member,
            record_type="custom",
            status=MedicalCase.Status.DRAFT,
            title=default_case_title,
            diagnosis_summary="",
            extra={"source": "workflow_auto_case"},
        )
        return member, medical_case, None

    @staticmethod
    def _value(payload, *keys, default=None):
        for key in keys:
            if key in payload and payload.get(key) not in (None, ""):
                return payload.get(key)
        return default

    def _create_medication_plan_bundle(
        self,
        *,
        request,
        member,
        items,
        medical_case=None,
        prescription=None,
        file_ids=None,
    ):
        created = []
        if not isinstance(items, list):
            items = []

        for idx, raw_item in enumerate(items):
            item = dict(raw_item or {})
            item_file_ids = self._pop_file_ids(item, "file_ids", "source_file_ids")
            medicine_box = None
            medicine_name = item.get("drug_name") or _("Unnamed medicine")

            box_source = item.get("medicine_box")
            existing_box_id = item.get("medicine_box_id")
            if existing_box_id not in (None, ""):
                if isinstance(box_source, dict):
                    return None, error_response(
                        msg={"medicine_box_id": [_("cannot combine medicine_box and medicine_box_id")]},
                        code=-1,
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    existing_box_id = int(existing_box_id)
                except (TypeError, ValueError):
                    return None, error_response(
                        msg={"medicine_box_id": [_("invalid medicine_box_id")]},
                        code=-1,
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
                accessible_ids = set(
                    family_medicine_cabinet_queryset(
                        user=request.user,
                        entry_member_id=member.id,
                    ).values_list("id", flat=True)
                )
                if existing_box_id not in accessible_ids:
                    return None, error_response(
                        msg={"medicine_box_id": [_("invalid medicine_box_id")]},
                        code=-1,
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    medicine_box = MedicineBox.objects.get(id=existing_box_id, is_deleted=False)
                except MedicineBox.DoesNotExist:
                    return None, error_response(
                        msg={"medicine_box_id": [_("invalid medicine_box_id")]},
                        code=-1,
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
            elif isinstance(box_source, dict):
                medicine_name = (
                    box_source.get("medicine_name")
                    or item.get("drug_name")
                    or _("Unnamed medicine")
                )
                box_file_ids = self._pop_file_ids(box_source, "file_ids", "source_file_ids")

                box_payload = {
                    "member": member.id,
                    "medicine_type": box_source.get("medicine_type"),
                    "medicine_name": medicine_name,
                    "brand_name": box_source.get("brand_name") or "",
                    "dosage_form": box_source.get("dosage_form") or "",
                    "strength": box_source.get("strength") or "",
                    "dose_unit": box_source.get("dose_unit") or item.get("dose_unit") or "片",
                    "total_quantity": box_source.get("total_quantity"),
                    "expire_date": box_source.get("expire_date"),
                    "notes": self._value(box_source, "notes") or "",
                    "extra": {**(box_source.get("extra") or {}), "source": "typed_upload"},
                }
                if box_file_ids:
                    box_payload["file_ids"] = box_file_ids
                box_serializer = MedicineBoxSerializer(data=box_payload, context={"request": request})
                validation_error = self._validate_or_error(box_serializer)
                if validation_error is not None:
                    return None, validation_error
                medicine_box = box_serializer.save(user=request.user)

            dose_unit = item.get("dose_unit") or (medicine_box.dose_unit if medicine_box else None) or "片"
            dose_per_time = item.get("dose_per_time") or (
                f"{item.get('dose_value')} {dose_unit}".strip()
                if item.get("dose_value") else ""
            ) or _("Follow medical advice")
            start_date = item.get("start_date") or timezone.localdate().isoformat()
            frequency_type = item.get("frequency_type") or MedicationPlan.FrequencyType.DAILY
            if frequency_type not in {choice[0] for choice in MedicationPlan.FrequencyType.choices}:
                frequency_type = MedicationPlan.FrequencyType.DAILY

            plan_payload = {
                "member": member.id,
                "medical_case": medical_case.id if medical_case else None,
                "medicine_box": medicine_box.id if medicine_box else None,
                "prescription": prescription.id if prescription else None,
                "drug_name": item.get("drug_name") or medicine_name,
                "dose_per_time": dose_per_time,
                "dose_value": item.get("dose_value"),
                "dose_unit": dose_unit,
                "frequency_type": frequency_type,
                "every_n_days": item.get("every_n_days"),
                "weekly_weekdays": item.get("weekly_weekdays") or [],
                "frequency_text": item.get("frequency_text") or _("Follow medical advice"),
                "reminder_times": item.get("reminder_times") or [],
                "start_date": start_date,
                "end_date": item.get("end_date"),
                "instructions": item.get("instructions") or "",
                "reminder_enabled": item.get("reminder_enabled", True),
                "status": self._value(item, "status", default=MedicationPlan.Status.ACTIVE),
                "extra": {**(item.get("extra") or {}), "source": "typed_upload", "sort_order": str(idx)},
            }
            plan_serializer = MedicationPlanSerializer(data=plan_payload, context={"request": request})
            validation_error = self._validate_or_error(plan_serializer)
            if validation_error is not None:
                return None, validation_error
            plan = plan_serializer.save(user=request.user)
            schedule_medication_plan_health_notification(
                actor_user=request.user,
                plan=plan,
                created=True,
            )
            self._bind_files(request.user, "medication_plan", plan.id, item_file_ids)
            created.append({
                "medicine_box_id": medicine_box.id if medicine_box else None,
                "medication_plan_id": plan.id,
            })

        if created and file_ids:
            business_type = "prescription_batch" if prescription else "medication_plan"
            business_id = prescription.id if prescription else created[0]["medication_plan_id"]
            self._bind_files(request.user, business_type, business_id, file_ids)
        return created, None

    def _save_prescriptions_batch(
        self,
        *,
        request,
        member,
        prescription_payloads,
        medical_case=None,
        prescription_source="prescription_batch_save",
    ):
        result = {
            "prescription_ids": [],
            "medicine_box_ids": [],
            "medication_plan_ids": [],
        }
        if not isinstance(prescription_payloads, list) or not prescription_payloads:
            return result, error_response(
                msg={"prescriptions": [_("no prescription items")]},
                code=-1,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        for prescription_payload in prescription_payloads:
            payload = dict(prescription_payload or {})
            file_ids = self._pop_file_ids(payload, "source_file_ids", "file_ids")
            items = payload.get("medication_plans") or []

            case_id = payload.get("medical_case")
            if case_id is None and medical_case is not None:
                case_id = medical_case.id
            plan_case = None
            if case_id:
                try:
                    plan_case = MedicalCase.objects.get(
                        id=case_id,
                        is_deleted=False,
                        member_id=member.id,
                    )
                except MedicalCase.DoesNotExist:
                    return result, error_response(
                        msg={"medical_case": [_("invalid medical_case")]},
                        code=-1,
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

            prescription_data = {
                "member": member.id,
                "medical_case": case_id,
                "prescriber_name": payload.get("prescriber_name", ""),
                "institution_name": payload.get("institution_name", ""),
                "prescribed_at": self._normalize_nullable_datetime(payload.get("prescribed_at")),
                "diagnosis": payload.get("diagnosis", ""),
                "prescription_no": payload.get("prescription_no"),
                "status": payload.get("status", Prescription.Status.ACTIVE),
                "extra": {**(payload.get("extra") or {}), "source": prescription_source},
            }
            prescription_serializer = PrescriptionSerializer(
                data=prescription_data,
                context={"request": request},
            )
            validation_error = self._validate_or_error(prescription_serializer)
            if validation_error is not None:
                return result, validation_error
            prescription = prescription_serializer.save(user=request.user)
            self._bind_files(request.user, "prescription_batch", prescription.id, file_ids)
            result["prescription_ids"].append(prescription.id)

            created, validation_error = self._create_medication_plan_bundle(
                request=request,
                member=member,
                items=items,
                medical_case=plan_case,
                prescription=prescription,
                file_ids=[],
            )
            if validation_error is not None:
                return result, validation_error
            for row in created or []:
                if row.get("medicine_box_id") is not None:
                    result["medicine_box_ids"].append(row["medicine_box_id"])
                result["medication_plan_ids"].append(row["medication_plan_id"])

        return result, None


class MedicalCaseWorkflowSaveView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        serializer = MedicalCaseSerializer(data=payload)
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "medical_case", obj.id, file_ids)
        return success_response(serializer.data, msg="saved", code=0, status_code=status.HTTP_201_CREATED)


class HealthExamWorkflowSaveView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        detail_rows = payload.pop("details", [])
        serializer = HealthExamReportSerializer(data=payload)
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)

        created_details = []
        for idx, detail in enumerate(detail_rows):
            detail_payload = {
                "business_type": MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
                "business_id": obj.id,
                "member": obj.member_id,
                "category": detail.get("category", ""),
                "sub_category": detail.get("sub_category") or detail.get("subCategory", ""),
                "item_name": detail.get("item_name") or detail.get("itemName", ""),
                "item_code": detail.get("item_code") or detail.get("itemCode", ""),
                "result_value": detail.get("result_value") or detail.get("resultValue", ""),
                "unit": detail.get("unit", ""),
                "reference_range": detail.get("reference_range") or detail.get("referenceRange", ""),
                "flag": detail.get("flag", ""),
                "result_at": detail.get("result_at")
                or detail.get("resultAt")
                or (f"{obj.exam_date.isoformat()}T00:00:00Z" if obj.exam_date else None),
                "modality": detail.get("modality", ""),
                "body_part": detail.get("body_part") or detail.get("bodyPart", ""),
                "diagnosis": detail.get("diagnosis", ""),
                "extra": detail.get("extra", {}),
                "sort_order": detail.get("sort_order", detail.get("sortOrder", idx)),
            }
            detail_serializer = MedExamDetailSerializer(data=detail_payload)
            validation_error = self._validate_or_error(detail_serializer)
            if validation_error is not None:
                return validation_error
            created = detail_serializer.save()
            created_details.append(MedExamDetailSerializer(created).data)

        self._bind_files(request.user, "health_exam_report", obj.id, file_ids)
        return success_response(
            {"id": obj.id, "report": HealthExamReportSerializer(obj).data, "details": created_details},
            msg="saved",
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class MedicalReportWorkflowSaveView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        detail_rows = payload.pop("details", [])

        report_payload = {
            "user": request.user.id,
            "member": payload.get("member"),
            "medical_record": payload.get("medical_case"),
            "category": payload.get("category", "") or "medical_report",
            "sub_category": "",
            "item_name": payload.get("title", "") or "医疗报告",
            "performed_at": payload.get("date"),
            "reported_at": payload.get("date"),
            "organization_name": payload.get("organization_name") or payload.get("hospital", "") or "",
            "department_name": "",
            "doctor_name": payload.get("doctor_name") or payload.get("doctor", "") or "",
            "findings": payload.get("content", "") or "",
            "impression": payload.get("content", "") or "",
            "source": ExaminationReport.Source.OCR,
            "raw_ocr": {"text": payload.get("content", "") or ""},
            "status": ExaminationReport.Status.DRAFT,
            "extra": {"source": "typed_upload"},
        }
        report_serializer = ExaminationReportSerializer(data=report_payload)
        validation_error = self._validate_or_error(report_serializer)
        if validation_error is not None:
            return validation_error
        report = report_serializer.save(user=request.user)

        created_details = []
        for idx, detail in enumerate(detail_rows):
            detail_payload = {
                "business_type": MedExamDetail.BusinessType.EXAMINATION_REPORT,
                "business_id": report.id,
                "member": report.member_id,
                "category": detail.get("category", "") or report.category,
                "sub_category": detail.get("sub_category", ""),
                "item_name": detail.get("item_name", "") or report.item_name,
                "item_code": detail.get("item_code", ""),
                "result_value": detail.get("result_value", ""),
                "unit": detail.get("unit", ""),
                "reference_range": detail.get("reference_range", ""),
                "flag": detail.get("flag", ""),
                "result_at": detail.get("result_at", report.reported_at),
                "modality": detail.get("modality", ""),
                "body_part": detail.get("body_part", ""),
                "diagnosis": detail.get("diagnosis", ""),
                "extra": detail.get("extra", {}),
                "sort_order": detail.get("sort_order", idx),
            }
            detail_serializer = MedExamDetailSerializer(data=detail_payload)
            validation_error = self._validate_or_error(detail_serializer)
            if validation_error is not None:
                return validation_error
            created = detail_serializer.save()
            created_details.append(MedExamDetailSerializer(created).data)

        self._bind_files(request.user, "examination_report", report.id, file_ids)
        return success_response(
            {"id": report.id, "report": ExaminationReportSerializer(report).data, "details": created_details},
            msg="saved",
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class SymptomWorkflowCreateView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        member, medical_case, resolve_error = self._resolve_member_and_case(request, payload, default_case_title="症状记录")
        if resolve_error is not None:
            return resolve_error

        symptom_payload = {
            "member": member.id,
            "medical_case": medical_case.id,
            "name": payload.get("name"),
            "code": payload.get("code", ""),
            "severity": payload.get("severity", ""),
            "started_at": self._normalize_nullable_datetime(payload.get("started_at")),
            "duration_value": payload.get("duration_value"),
            "duration_unit": payload.get("duration_unit", ""),
            "body_part": payload.get("body_part", ""),
            "notes": payload.get("notes", ""),
            "extra": payload.get("extra", {}),
        }
        serializer = SymptomSerializer(data=symptom_payload, context={"request": request})
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "symptom", obj.id, file_ids)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class VisitWorkflowCreateView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        member, medical_case, resolve_error = self._resolve_member_and_case(request, payload, default_case_title="就诊记录")
        if resolve_error is not None:
            return resolve_error

        visit_payload = {
            "member": member.id,
            "medical_case": medical_case.id,
            "visit_type": payload.get("visit_type", "") or "custom",
            "visited_at": self._normalize_nullable_datetime(payload.get("visited_at")),
            "department": payload.get("department", ""),
            "doctor_name": payload.get("doctor_name", ""),
            "visit_no": payload.get("visit_no", ""),
            "notes": payload.get("notes", ""),
            "extra": payload.get("extra", {}),
        }
        serializer = VisitSerializer(data=visit_payload, context={"request": request})
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "visit", obj.id, file_ids)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class SurgeryWorkflowCreateView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        member, medical_case, resolve_error = self._resolve_member_and_case(request, payload, default_case_title="手术记录")
        if resolve_error is not None:
            return resolve_error

        surgery_payload = {
            "member": member.id,
            "medical_case": medical_case.id,
            "procedure_name": payload.get("procedure_name"),
            "procedure_code": payload.get("procedure_code", ""),
            "site": payload.get("site", ""),
            "performed_at": self._normalize_nullable_datetime(payload.get("performed_at")),
            "surgeon": payload.get("surgeon", ""),
            "anesthesia_type": payload.get("anesthesia_type", ""),
            "incision_level": payload.get("incision_level", ""),
            "asa_class": payload.get("asa_class", ""),
            "notes": payload.get("notes", ""),
            "extra": payload.get("extra", {}),
        }
        serializer = SurgerySerializer(data=surgery_payload, context={"request": request})
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "surgery", obj.id, file_ids)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class FollowUpWorkflowCreateView(_WorkflowBaseAPIView):
    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", [])
        member, medical_case, resolve_error = self._resolve_member_and_case(request, payload, default_case_title="随访记录")
        if resolve_error is not None:
            return resolve_error

        follow_up_payload = {
            "member": member.id,
            "medical_case": medical_case.id,
            "planned_at": self._normalize_nullable_datetime(payload.get("planned_at")),
            "completed_at": self._normalize_nullable_datetime(payload.get("completed_at")),
            "status": payload.get("status", "") or "initial",
            "method": payload.get("method", ""),
            "outcome": payload.get("outcome", ""),
            "next_action": payload.get("next_action", ""),
            "extra": payload.get("extra", {}),
        }
        serializer = FollowUpSerializer(data=follow_up_payload, context={"request": request})
        validation_error = self._validate_or_error(serializer)
        if validation_error is not None:
            return validation_error
        obj = serializer.save(user=request.user)
        self._bind_files(request.user, "follow_up", obj.id, file_ids)
        return success_response(serializer.data, msg="created", code=0, status_code=status.HTTP_201_CREATED)


class MedicalAttachmentBatchBindView(_WorkflowBaseAPIView):
    @transaction.atomic
    def patch(self, request):
        items = request.data.get("items", [])
        updated = 0
        for item in items:
            file_id = item.get("file_id")
            business_type = item.get("business_type")
            business_id = item.get("business_id")
            if not file_id or not business_type or business_id is None:
                continue
            from file_manager.business_access import user_can_access_business, user_can_access_file

            file_record = (
                ManagedFile.objects.filter(id=file_id, is_deleted=False)
                .prefetch_related("business_relations")
                .first()
            )
            if file_record and user_can_access_file(request.user, file_record):
                if user_can_access_business(request.user, business_type, business_id):
                    bind_file_to_business(request.user, file_record, business_type, business_id)
                updated += 1
        return success_response({"updated": updated}, msg="updated", code=0, status_code=status.HTTP_200_OK)


class MedicationPlanWorkflowSaveView(_WorkflowBaseAPIView):
    """保存用药计划抽取结果：每条结果同步创建 MedicineBox + MedicationPlan，可选创建/关联 Prescription。"""

    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        file_ids = payload.pop("file_ids", []) or []
        member_id = payload.get("member")
        if not member_id:
            return error_response(msg={"member": [_("member is required")]}, code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        try:
            binding = MemberPermissionGate.require_write(user=request.user, member_id=member_id)
        except PermissionError:
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        member = binding.member

        medical_case = None
        medical_case_id = payload.get("medical_case")
        if medical_case_id:
            try:
                medical_case = MedicalCase.objects.get(id=medical_case_id, is_deleted=False, member_id=member.id)
            except MedicalCase.DoesNotExist:
                return error_response(msg={"medical_case": [_("invalid medical_case")]}, code=-1, status_code=status.HTTP_400_BAD_REQUEST)
            if medical_case.member_id != member.id:
                return error_response(msg={"medical_case": [_("medical_case does not belong to member")]}, code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        prescription = None
        prescription_payload = payload.get("prescription")
        if prescription_payload:
            prescription_data = dict(prescription_payload or {})
            prescription_data["member"] = member.id
            if medical_case:
                prescription_data["medical_case"] = medical_case.id
            prescription_serializer = PrescriptionSerializer(data=prescription_data, context={"request": request})
            validation_error = self._validate_or_error(prescription_serializer)
            if validation_error is not None:
                return validation_error
            prescription = prescription_serializer.save(user=request.user)
        elif payload.get("prescription_id"):
            try:
                prescription = Prescription.objects.get(
                    id=payload.get("prescription_id"),
                    member_id=member.id,
                    is_deleted=False,
                )
            except Prescription.DoesNotExist:
                return error_response(msg={"prescription": [_("invalid prescription")]}, code=-1, status_code=status.HTTP_400_BAD_REQUEST)
            if prescription.member_id != member.id:
                return error_response(msg={"prescription": [_("prescription does not belong to member")]}, code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        created, validation_error = self._create_medication_plan_bundle(
            request=request,
            member=member,
            items=payload.get("items") or [],
            medical_case=medical_case,
            prescription=prescription,
            file_ids=file_ids,
        )
        if validation_error is not None:
            return validation_error
        if not created:
            return error_response(msg={"items": [_("no medication plan items")]}, code=-1, status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(
            {
                "id": created[0]["medication_plan_id"],
                "prescription_id": prescription.id if prescription else None,
                "items": created,
            },
            msg="saved",
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class PrescriptionBatchWorkflowSaveView(_WorkflowBaseAPIView):
    """批量保存处方识别结果：每条处方同步创建 Prescription + MedicineBox + MedicationPlan，不创建病历。"""

    @transaction.atomic
    def post(self, request):
        payload = request.data.copy()
        member_id = payload.get("member")
        if not member_id:
            return error_response(
                msg={"member": [_("member is required")]},
                code=-1,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            binding = MemberPermissionGate.require_write(user=request.user, member_id=member_id)
        except PermissionError:
            return error_response(
                msg="permission_denied",
                code=-1,
                status_code=status.HTTP_403_FORBIDDEN,
            )

        result, validation_error = self._save_prescriptions_batch(
            request=request,
            member=binding.member,
            prescription_payloads=payload.get("prescriptions") or [],
            medical_case=None,
            prescription_source="prescription_batch_save",
        )
        if validation_error is not None:
            return validation_error

        return success_response(
            {
                "member_id": binding.member.id,
                **result,
            },
            msg="saved",
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class CombinedMedicalCreateAPIView(_WorkflowBaseAPIView):
    """
    一次性创建完整医疗记录（组合创建 API）。

    流程：
    1) member: 若带 id → 校验存在与归属；否则创建；得到 member_id
    2) medical_case: 必传，使用 member_id 创建；得到 case_id
    3) symptom/visit/surgery/follow-up/examination_reports: 可选，有则使用 case_id 逐一创建
    4) 返回统一结果（已创建对象的精简信息/主键）

    参考：HealthClient 的 SeverMedicalCreateAPI 和 ZhaodkDream 的 SeverMedicalCreateAPI
    """
    _NULLISH_DATETIME_TOKENS = {"", "无", "未提及", "未知", "none", "null", "n/a", "na", "-", "--"}

    @classmethod
    def _normalize_nullable_datetime(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed.lower() in cls._NULLISH_DATETIME_TOKENS or trimmed in cls._NULLISH_DATETIME_TOKENS:
                return None
            return trimmed
        return value

    @transaction.atomic
    def post(self, request):
        data = request.data or {}

        # ------ (0) 基本校验：member + medical_case 必须提供 ------
        member_payload = data.get("member")
        case_payload = data.get("medical_case")

        if not member_payload or not case_payload:
            return Response(
                {"detail": "member 与 medical_case 均为必填"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # =========================================================
        # (1) 处理成员：若带 id → 校验并取用；否则创建
        # =========================================================
        member_id = member_payload.get("id")
        if member_id:
            # 有 id：校验成员存在 & 归属权限
            try:
                member_obj = Member.objects.get(pk=member_id, is_deleted=False)
            except Member.DoesNotExist:
                return Response(
                    {"detail": f"成员(id={member_id})不存在"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not request.user.is_staff:
                try:
                    MemberPermissionGate.require_write(user=request.user, member_id=member_obj.id)
                except PermissionError:
                    return Response({"detail": "无权编辑该成员医疗资料"}, status=status.HTTP_403_FORBIDDEN)
        else:
            # 无 id：创建成员
            ser_m = MemberSerializer(data=member_payload, context={"request": request})
            ser_m.is_valid(raise_exception=True)
            # user 在 Serializer 中为 read_only，须通过 save(user=…) 写入（见 DRF ModelSerializer.save）
            member_obj = ser_m.save(user=request.user)

        member_id = member_obj.id

        # =========================================================
        # (2) 处理病历 MedicalCase：必须
        # =========================================================
        case_payload = dict(case_payload)
        case_file_ids = self._pop_file_ids(case_payload, "source_file_ids", "file_ids")
        legacy_source_file_ids = data.get("source_file_ids") or []
        if isinstance(legacy_source_file_ids, list):
            case_file_ids = list(dict.fromkeys(case_file_ids + legacy_source_file_ids))
        case_payload["member"] = member_id
        case_ser = MedicalCaseSerializer(data=case_payload, context={"request": request})
        case_ser.is_valid(raise_exception=True)
        case_obj = case_ser.save(user=request.user)
        case_id = case_obj.id
        self._bind_files(request.user, "medical_case", case_id, case_file_ids)

        # =========================================================
        # (3) 可选创建：symptom/visit/surgery/follow-up/examination_reports
        # =========================================================
        result = {
            "member_id": member_id,
            "medical_case_id": case_id,
            "created_at": timezone.now().isoformat(),
        }

        # ---------- symptom（单个，可选）----------
        symptom_payload = data.get("symptom")
        if symptom_payload:
            payload = dict(symptom_payload)
            file_ids = self._pop_file_ids(payload, "source_file_ids", "file_ids")
            payload["started_at"] = self._normalize_nullable_datetime(payload.get("started_at"))
            payload["member"] = member_id
            payload["medical_case"] = case_id
            ser = SymptomSerializer(data=payload, context={"request": request})
            ser.is_valid(raise_exception=True)
            obj = ser.save(user=request.user)
            self._bind_files(request.user, "symptom", obj.id, file_ids)
            result["symptom_id"] = obj.id

        # ---------- visit（单个，可选）----------
        visit_payload = data.get("visit")
        if visit_payload:
            payload = dict(visit_payload)
            file_ids = self._pop_file_ids(payload, "source_file_ids", "file_ids")
            payload["visited_at"] = self._normalize_nullable_datetime(payload.get("visited_at"))
            payload["member"] = member_id
            payload["medical_case"] = case_id
            ser = VisitSerializer(data=payload, context={"request": request})
            ser.is_valid(raise_exception=True)
            obj = ser.save(user=request.user)
            self._bind_files(request.user, "visit", obj.id, file_ids)
            result["visit_id"] = obj.id

        # ---------- surgery（单个，可选）----------
        surgery_payload = data.get("surgery")
        if surgery_payload:
            payload = dict(surgery_payload)
            file_ids = self._pop_file_ids(payload, "source_file_ids", "file_ids")
            payload["performed_at"] = self._normalize_nullable_datetime(payload.get("performed_at"))
            payload["member"] = member_id
            payload["medical_case"] = case_id
            ser = SurgerySerializer(data=payload, context={"request": request})
            ser.is_valid(raise_exception=True)
            obj = ser.save(user=request.user)
            self._bind_files(request.user, "surgery", obj.id, file_ids)
            result["surgery_id"] = obj.id

        # ---------- follow_up（单个，可选）----------
        follow_up_payload = data.get("follow_up")
        if follow_up_payload:
            payload = dict(follow_up_payload)
            file_ids = self._pop_file_ids(payload, "source_file_ids", "file_ids")
            payload["planned_at"] = self._normalize_nullable_datetime(payload.get("planned_at"))
            payload["completed_at"] = self._normalize_nullable_datetime(payload.get("completed_at"))
            payload["member"] = member_id
            payload["medical_case"] = case_id
            ser = FollowUpSerializer(data=payload, context={"request": request})
            ser.is_valid(raise_exception=True)
            obj = ser.save(user=request.user)
            self._bind_files(request.user, "follow_up", obj.id, file_ids)
            result["follow_up_id"] = obj.id

        # ---------- examination_reports（批量，可选）----------
        exam_reports_payload = data.get("examination_reports") or []
        if isinstance(exam_reports_payload, list) and exam_reports_payload:
            result["examination_report_ids"] = []
            for rep in exam_reports_payload:
                payload = dict(rep or {})
                file_ids = self._pop_file_ids(payload, "source_file_ids", "file_ids")
                payload["performed_at"] = self._normalize_nullable_datetime(payload.get("performed_at"))
                payload["reported_at"] = self._normalize_nullable_datetime(payload.get("reported_at"))
                payload["member"] = member_id
                # ExaminationReport 模型使用 medical_record 字段名（不是 medical_case）
                payload["medical_record"] = case_id
                # details 单独处理
                details = payload.pop("details", [])

                ser = ExaminationReportSerializer(data=payload, context={"request": request})
                ser.is_valid(raise_exception=True)
                obj = ser.save(user=request.user)
                self._bind_files(request.user, "examination_report", obj.id, file_ids)
                result["examination_report_ids"].append(obj.id)

                # 创建明细
                for idx, detail in enumerate(details):
                    normalized_detail = dict(detail or {})
                    normalized_detail["result_at"] = self._normalize_nullable_datetime(normalized_detail.get("result_at"))
                    detail_payload = {
                        "business_type": MedExamDetail.BusinessType.EXAMINATION_REPORT,
                        "business_id": obj.id,
                        "member": member_id,
                        **normalized_detail,
                    }
                    detail_ser = MedExamDetailSerializer(data=detail_payload, context={"request": request})
                    detail_ser.is_valid(raise_exception=True)
                    detail_ser.save()

        # ---------- prescriptions / medication_plans（批量，可选）----------
        prescription_payloads = data.get("prescriptions") or []
        if isinstance(prescription_payloads, list) and prescription_payloads:
            batch_result, validation_error = self._save_prescriptions_batch(
                request=request,
                member=member_obj,
                prescription_payloads=prescription_payloads,
                medical_case=case_obj,
                prescription_source="combined_create",
            )
            if validation_error is not None:
                return validation_error
            result.update(batch_result)

        return Response(result, status=status.HTTP_201_CREATED)
