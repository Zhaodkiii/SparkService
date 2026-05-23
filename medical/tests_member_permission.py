from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import AccountProfile
from medical.models import Member, UserMemberBinding
from medical.services import member_binding_service as binding_service
from medical.services.member_invite_service import normalize_phone_for_lookup, resolve_user_by_contact
from medical.services.member_permission_levels import permission_to_role, role_to_permission

User = get_user_model()


class MemberPermissionLevelTests(APITestCase):
    def test_role_permission_mapping(self):
        self.assertEqual(role_to_permission(UserMemberBinding.Role.EDITOR), "edit")
        self.assertEqual(permission_to_role("manage"), UserMemberBinding.Role.ADMIN)
        self.assertEqual(permission_to_role("edit"), UserMemberBinding.Role.EDITOR)

    def test_normalize_phone_cn_local(self):
        e164 = normalize_phone_for_lookup(phone="15385056020", country_code="+86")
        self.assertEqual(e164, "+8615385056020")

    def test_resolve_user_by_e164_phone(self):
        user = User.objects.create_user(username="phoneuser", email="p@example.com", password="pass12345")
        AccountProfile.objects.create(user=user, phone_number="+8615385056020")
        matched, normalized = resolve_user_by_contact(
            channel="phone",
            contact="15385056020",
            country_code="+86",
        )
        self.assertEqual(normalized, "+8615385056020")
        self.assertEqual(matched, user)

    def test_share_ticket_defaults_to_edit_permission(self):
        owner = User.objects.create_user(username="owner2", email="o2@example.com", password="pass12345")
        self.client.force_authenticate(owner)
        create_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "李四", "gender": "male", "relationship": "self"},
            format="json",
        )
        member_id = create_resp.json()["data"]["id"]
        ticket_resp = self.client.post(
            f"/api/v1/medical/members/{member_id}/share-ticket/",
            {"channel": "qr"},
            format="json",
        )
        self.assertEqual(ticket_resp.status_code, status.HTTP_200_OK)
        ticket = ticket_resp.json()["data"]["share_ticket"]
        from medical.services import member_share_ticket as share_ticket_service

        payload = share_ticket_service.unsign_ticket(ticket)
        self.assertEqual(payload["role"], UserMemberBinding.Role.EDITOR)

    def test_patch_binding_permission_owner_only(self):
        owner = User.objects.create_user(username="owner3", email="o3@example.com", password="pass12345")
        guest = User.objects.create_user(username="guest3", email="g3@example.com", password="pass12345")
        self.client.force_authenticate(owner)
        create_resp = self.client.post(
            "/api/v1/medical/members/",
            {"name": "王五", "gender": "male", "relationship": "self"},
            format="json",
        )
        member_id = create_resp.json()["data"]["id"]
        ticket_resp = self.client.post(
            f"/api/v1/medical/members/{member_id}/share-ticket/",
            {"channel": "qr", "permission": "view"},
            format="json",
        )
        ticket = ticket_resp.json()["data"]["share_ticket"]
        self.client.force_authenticate(guest)
        self.client.post(
            "/api/v1/medical/member-share-ticket/accept/",
            {"share_ticket": ticket, "relationship": "friend"},
            format="json",
        )
        guest_binding = binding_service.get_active_binding(user=guest, member_id=member_id)
        self.assertIsNotNone(guest_binding)

        self.client.force_authenticate(guest)
        denied = self.client.patch(
            f"/api/v1/medical/member-bindings/{guest_binding.id}/permission/",
            {"permission": "edit"},
            format="json",
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(owner)
        ok = self.client.patch(
            f"/api/v1/medical/member-bindings/{guest_binding.id}/permission/",
            {"permission": "edit"},
            format="json",
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.json()["data"]["permission"], "edit")
