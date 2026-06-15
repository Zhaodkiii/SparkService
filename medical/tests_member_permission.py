from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import SocialIdentity
from medical.models import Member, MemberShareInvite, UserMemberBinding
from medical.services import member_binding_service as binding_service
from medical.services.member_invite_delivery import DeliveryResult
from medical.services.member_invite_service import (
    create_invite,
    normalize_phone_for_lookup,
    resolve_user_by_contact,
)
from medical.services.member_permission_levels import permission_to_role, role_to_permission

User = get_user_model()

BUNDLE_HEALTH = "cn.Zhaodk.Health"
BUNDLE_AERA = "cn.Zhaodk.Aera"
PHONE_E164 = "+8615385056020"


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
        SocialIdentity.objects.create(
            user=user,
            bundle_id="cn.Zhaodk.Health",
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8615385056020",
        )
        matched, normalized = resolve_user_by_contact(
            channel="phone",
            contact="15385056020",
            country_code="+86",
            bundle_id="cn.Zhaodk.Health",
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


class MemberInviteBundleIsolationTests(APITestCase):
    """MEMBER-INVITE-000001: 远程邀请联系人匹配按 bundle_id 隔离。"""

    def setUp(self):
        self.health_user = User.objects.create_user(
            username="health_user",
            email="health@example.com",
            password="pass12345",
        )
        self.aera_user = User.objects.create_user(
            username="aera_user",
            email="aera@example.com",
            password="pass12345",
        )
        SocialIdentity.objects.create(
            user=self.health_user,
            bundle_id=BUNDLE_HEALTH,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid=PHONE_E164,
        )
        SocialIdentity.objects.create(
            user=self.aera_user,
            bundle_id=BUNDLE_AERA,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid=PHONE_E164,
        )

    def test_same_phone_matches_health_bundle_only(self):
        matched, normalized = resolve_user_by_contact(
            channel="phone",
            contact="15385056020",
            country_code="+86",
            bundle_id=BUNDLE_HEALTH,
        )
        self.assertEqual(normalized, PHONE_E164)
        self.assertEqual(matched, self.health_user)

    def test_same_phone_matches_aera_bundle_only(self):
        matched, normalized = resolve_user_by_contact(
            channel="phone",
            contact="15385056020",
            country_code="+86",
            bundle_id=BUNDLE_AERA,
        )
        self.assertEqual(normalized, PHONE_E164)
        self.assertEqual(matched, self.aera_user)

    def test_phone_missing_in_current_bundle_returns_null(self):
        matched, normalized = resolve_user_by_contact(
            channel="phone",
            contact="15385056020",
            country_code="+86",
            bundle_id="cn.Zhaodk.Other",
        )
        self.assertEqual(normalized, PHONE_E164)
        self.assertIsNone(matched)

    def test_phone_without_bundle_id_does_not_match_globally(self):
        matched, normalized = resolve_user_by_contact(
            channel="phone",
            contact="15385056020",
            country_code="+86",
            bundle_id="",
        )
        self.assertEqual(normalized, PHONE_E164)
        self.assertIsNone(matched)

    def test_email_matches_only_when_user_has_bundle_social_identity(self):
        email = "shared@example.com"
        user = User.objects.create_user(
            username="health_email_user",
            email=email,
            password="pass12345",
        )
        SocialIdentity.objects.create(
            user=user,
            bundle_id=BUNDLE_HEALTH,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple.health.shared@example.com",
        )

        matched_health, normalized = resolve_user_by_contact(
            channel="email",
            contact=email,
            bundle_id=BUNDLE_HEALTH,
        )
        matched_aera, _ = resolve_user_by_contact(
            channel="email",
            contact=email,
            bundle_id=BUNDLE_AERA,
        )
        self.assertEqual(normalized, email)
        self.assertEqual(matched_health, user)
        self.assertIsNone(matched_aera)

    def test_duplicate_email_prefers_user_with_bundle_social_identity(self):
        email = "97621528@qq.com"
        admin_user = User.objects.create_user(
            username="Zhaodk",
            email=email,
            password="pass12345",
        )
        admin_user.is_staff = True
        admin_user.save(update_fields=["is_staff"])
        health_user = User.objects.create_user(
            username="apple_000082",
            email=email,
            password="pass12345",
        )
        SocialIdentity.objects.create(
            user=health_user,
            bundle_id=BUNDLE_HEALTH,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="000082.58f2a98183e84bfbb26777c41c443af9.1112",
        )

        matched, normalized = resolve_user_by_contact(
            channel="email",
            contact=email,
            bundle_id=BUNDLE_HEALTH,
        )
        self.assertEqual(normalized, email)
        self.assertEqual(matched, health_user)
        self.assertNotEqual(matched, admin_user)

    def test_email_cross_bundle_matches_respective_social_identity_users(self):
        email = "crossbundle@example.com"
        health_user = User.objects.create_user(
            username="health_cross",
            email=email,
            password="pass12345",
        )
        aera_user = User.objects.create_user(
            username="aera_cross",
            email=email,
            password="pass12345",
        )
        SocialIdentity.objects.create(
            user=health_user,
            bundle_id=BUNDLE_HEALTH,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple.health.cross",
        )
        SocialIdentity.objects.create(
            user=aera_user,
            bundle_id=BUNDLE_AERA,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple.aera.cross",
        )

        matched_health, _ = resolve_user_by_contact(
            channel="email",
            contact=email,
            bundle_id=BUNDLE_HEALTH,
        )
        matched_aera, _ = resolve_user_by_contact(
            channel="email",
            contact=email,
            bundle_id=BUNDLE_AERA,
        )
        self.assertEqual(matched_health, health_user)
        self.assertEqual(matched_aera, aera_user)

    def test_email_without_bundle_identity_returns_null(self):
        email = "orphan@example.com"
        User.objects.create_user(username="orphan", email=email, password="pass12345")
        matched, normalized = resolve_user_by_contact(
            channel="email",
            contact=email,
            bundle_id=BUNDLE_HEALTH,
        )
        self.assertEqual(normalized, email)
        self.assertIsNone(matched)

    def test_create_invite_dedup_requires_matching_role_and_contact(self):
        inviter = User.objects.create_user(username="inviter", email="i@example.com", password="pass12345")
        member = Member.objects.create(name="测试成员", gender="male", user=inviter)
        binding_service.create_owner_binding(user=inviter, member=member, relationship="self")

        first = create_invite(
            member=member,
            inviter=inviter,
            target_user=self.health_user,
            channel=MemberShareInvite.Channel.PHONE,
            role=UserMemberBinding.Role.EDITOR,
            target_contact=PHONE_E164,
        )
        second = create_invite(
            member=member,
            inviter=inviter,
            target_user=self.aera_user,
            channel=MemberShareInvite.Channel.PHONE,
            role=UserMemberBinding.Role.EDITOR,
            target_contact=PHONE_E164,
        )
        third = create_invite(
            member=member,
            inviter=inviter,
            target_user=self.health_user,
            channel=MemberShareInvite.Channel.PHONE,
            role=UserMemberBinding.Role.VIEWER,
            target_contact=PHONE_E164,
        )
        self.assertNotEqual(first.id, second.id)
        self.assertNotEqual(first.id, third.id)

    @patch("medical.services.member_invite_delivery._deliver")
    def test_invite_api_uses_token_bundle_for_phone_match(self, deliver_mock):
        deliver_mock.return_value = DeliveryResult("sms", "sent", "ok")
        inviter = User.objects.create_user(username="inviter_api", email="ia@example.com", password="pass12345")
        member = Member.objects.create(name="API成员", gender="male", user=inviter)
        binding_service.create_owner_binding(user=inviter, member=member, relationship="self")

        token = AccessToken.for_user(inviter)
        token["bundle_id"] = BUNDLE_HEALTH
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.post(
            f"/api/v1/medical/members/{member.id}/invites/",
            {
                "channel": "phone",
                "phone": "15385056020",
                "country_code": "+86",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(data["matched_user_id"], self.health_user.id)
        self.assertEqual(data["normalized_phone"], PHONE_E164)

    @patch("medical.services.member_invite_delivery._deliver")
    def test_invite_api_no_match_in_bundle_allows_sms_direct(self, deliver_mock):
        deliver_mock.return_value = DeliveryResult("sms", "sent", "ok")
        inviter = User.objects.create_user(username="inviter_api2", email="ib@example.com", password="pass12345")
        member = Member.objects.create(name="API成员2", gender="male", user=inviter)
        binding_service.create_owner_binding(user=inviter, member=member, relationship="self")

        token = AccessToken.for_user(inviter)
        token["bundle_id"] = "cn.Zhaodk.Other"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.post(
            f"/api/v1/medical/members/{member.id}/invites/",
            {
                "channel": "phone",
                "phone": "15385056020",
                "country_code": "+86",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertIsNone(data["matched_user_id"])
        self.assertEqual(data["normalized_phone"], PHONE_E164)
        invite = MemberShareInvite.objects.get(id=data["invite_id"])
        self.assertIsNone(invite.target_user_id)
