"""智能体头像（BACKOFFICE-HOSPITAL-AGENT-000002）服务端测试。"""

from __future__ import annotations

import uuid

from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from file_manager.business_relations import bind_file_to_business
from file_manager.constants import (
    AGENT_AVATAR_KEY_TEMPLATE,
    BUSINESS_TYPE_CLINICAL_AGENT_AVATAR,
)
from file_manager.models import ManagedFile, ManagedFileBusinessRelation
from hospital_care.api.presenters import agent_public
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalAgentProfile
from hospital_care.services.agent_avatar_service import (
    resolve_agent_avatar,
    resolve_valid_agent_avatar_file,
    set_agent_avatar,
)
from hospital_care.services.agent_provisioning_service import create_clinical_agent
from hospital_care.tests.factories import (
    DummyRequest,
    make_agent,
    make_department,
    make_doctor,
    make_hospital,
    make_provider,
    make_user,
)

OSS_SETTINGS = {
    "ALIYUN_OSS_ENDPOINT": "https://oss-cn-test.aliyuncs.com",
    "ALIYUN_OSS_BUCKET": "test-bucket",
    "CLINICAL_AGENT_DEFAULT_AVATAR_URL": "https://cdn.test/default-avatar.png",
    "CLINICAL_AGENT_DEFAULT_AVATAR_VERSION": "v1",
}


def make_avatar_file(hospital, user, *, business_id="", mime_type="image/webp", hospital_id=None) -> ManagedFile:
    file_uuid = uuid.uuid4()
    object_key = AGENT_AVATAR_KEY_TEMPLATE.format(hospital_id=hospital_id or hospital.id, file_uuid=file_uuid)
    record = ManagedFile.objects.create(
        user=user,
        file_uuid=file_uuid,
        original_name="avatar.webp",
        file_ext="webp",
        mime_type=mime_type,
        file_size=1024,
        is_public=True,
        object_key=object_key,
        storage_type="oss",
    )
    bind_file_to_business(user, record, BUSINESS_TYPE_CLINICAL_AGENT_AVATAR, business_id)
    return record


@override_settings(**OSS_SETTINGS)
class AgentAvatarModelTests(TestCase):
    def setUp(self):
        self.user = make_user("avatar-owner")
        self.hospital = make_hospital(code="AV-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)

    def test_agent_defaults_to_doctor_source(self):
        agent = make_agent(self.hospital, self.doctor, self.department)
        self.assertEqual(agent.avatar_source, ClinicalAgentProfile.AvatarSource.DOCTOR)
        self.assertIsNone(agent.avatar_file_id)

    def test_constraint_rejects_doctor_with_file(self):
        file_record = make_avatar_file(self.hospital, self.user)
        with self.assertRaises(IntegrityError):
            ClinicalAgentProfile.objects.create(
                hospital=self.hospital,
                doctor=self.doctor,
                department=self.department,
                scenario_binding=make_agent(self.hospital, self.doctor, self.department).scenario_binding,
                name="非法智能体",
                avatar_source=ClinicalAgentProfile.AvatarSource.DOCTOR,
                avatar_file=file_record,
            )

    def test_constraint_rejects_custom_without_file(self):
        base = make_agent(self.hospital, self.doctor, self.department)
        with self.assertRaises(IntegrityError):
            ClinicalAgentProfile.objects.create(
                hospital=self.hospital,
                doctor=self.doctor,
                department=self.department,
                scenario_binding=base.scenario_binding,
                name="非法智能体2",
                avatar_source=ClinicalAgentProfile.AvatarSource.CUSTOM,
                avatar_file=None,
            )

    def test_resolve_doctor_source_reads_doctor_avatar(self):
        doctor_file = make_avatar_file(self.hospital, self.user)
        self.doctor.avatar_file = doctor_file
        self.doctor.save(update_fields=["avatar_file"])
        agent = make_agent(self.hospital, self.doctor, self.department)

        resolved = resolve_agent_avatar(agent)
        self.assertEqual(resolved.version, f"doctor:{doctor_file.id}:{doctor_file.file_uuid}")
        self.assertIn(str(doctor_file.file_uuid), resolved.url)
        self.assertIn("v=", resolved.url)

    def test_resolve_doctor_without_avatar_falls_back_to_default(self):
        agent = make_agent(self.hospital, self.doctor, self.department)
        resolved = resolve_agent_avatar(agent)
        self.assertEqual(resolved.url, "https://cdn.test/default-avatar.png")
        self.assertEqual(resolved.version, "default:v1")

    def test_resolve_custom_source(self):
        agent = make_agent(self.hospital, self.doctor, self.department)
        file_record = make_avatar_file(self.hospital, self.user)
        agent.avatar_source = ClinicalAgentProfile.AvatarSource.CUSTOM
        agent.avatar_file = file_record
        agent.save(update_fields=["avatar_source", "avatar_file"])

        resolved = resolve_agent_avatar(agent)
        self.assertEqual(resolved.version, f"custom:{file_record.id}:{file_record.file_uuid}")

    def test_resolve_custom_missing_file_falls_back_to_default_not_doctor(self):
        doctor_file = make_avatar_file(self.hospital, self.user)
        self.doctor.avatar_file = doctor_file
        self.doctor.save(update_fields=["avatar_file"])
        agent = make_agent(self.hospital, self.doctor, self.department)
        custom_file = make_avatar_file(self.hospital, self.user)
        agent.avatar_source = ClinicalAgentProfile.AvatarSource.CUSTOM
        agent.avatar_file = custom_file
        agent.save(update_fields=["avatar_source", "avatar_file"])
        # 文件被标记删除（不应发生，但解析必须稳健）
        custom_file.soft_delete()

        resolved = resolve_agent_avatar(agent)
        self.assertEqual(resolved.version, "default:v1")
        self.assertNotIn(str(doctor_file.file_uuid), resolved.url)


@override_settings(**OSS_SETTINGS)
class ResolveValidAvatarFileTests(TestCase):
    def setUp(self):
        self.user = make_user("avatar-check")
        self.hospital = make_hospital(code="AVC-H")
        self.other_hospital = make_hospital(code="AVC-H2")

    def test_valid_file_accepted(self):
        record = make_avatar_file(self.hospital, self.user)
        resolved = resolve_valid_agent_avatar_file(hospital=self.hospital, file_id=record.id)
        self.assertEqual(resolved.id, record.id)

    def test_missing_file_rejected(self):
        with self.assertRaises(HospitalCareError) as ctx:
            resolve_valid_agent_avatar_file(hospital=self.hospital, file_id=999999)
        self.assertEqual(ctx.exception.error_code, "AVATAR_FILE_NOT_FOUND")

    def test_empty_file_id_rejected(self):
        with self.assertRaises(HospitalCareError) as ctx:
            resolve_valid_agent_avatar_file(hospital=self.hospital, file_id=None)
        self.assertEqual(ctx.exception.error_code, "AVATAR_SOURCE_INVALID")

    def test_non_webp_rejected(self):
        record = make_avatar_file(self.hospital, self.user, mime_type="image/png")
        with self.assertRaises(HospitalCareError) as ctx:
            resolve_valid_agent_avatar_file(hospital=self.hospital, file_id=record.id)
        self.assertEqual(ctx.exception.error_code, "AVATAR_FILE_FORBIDDEN")

    def test_cross_hospital_rejected(self):
        record = make_avatar_file(self.hospital, self.user, hospital_id=self.other_hospital.id)
        with self.assertRaises(HospitalCareError) as ctx:
            resolve_valid_agent_avatar_file(hospital=self.hospital, file_id=record.id)
        self.assertEqual(ctx.exception.error_code, "AVATAR_FILE_FORBIDDEN")

    def test_file_without_avatar_relation_rejected(self):
        record = ManagedFile.objects.create(
            user=self.user,
            original_name="x.webp",
            mime_type="image/webp",
            file_size=1,
            object_key=AGENT_AVATAR_KEY_TEMPLATE.format(hospital_id=self.hospital.id, file_uuid=uuid.uuid4()),
        )
        with self.assertRaises(HospitalCareError) as ctx:
            resolve_valid_agent_avatar_file(hospital=self.hospital, file_id=record.id)
        self.assertEqual(ctx.exception.error_code, "AVATAR_FILE_FORBIDDEN")


@override_settings(**OSS_SETTINGS)
class SetAgentAvatarTests(TestCase):
    def setUp(self):
        self.user = make_user("avatar-set")
        self.hospital = make_hospital(code="AVS-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)

    def test_custom_avatar_takes_effect_immediately(self):
        file_record = make_avatar_file(self.hospital, self.user)
        updated = set_agent_avatar(
            agent_id=self.agent.id,
            avatar_source="custom",
            avatar_file_id=file_record.id,
            version=self.agent.version,
        )
        self.assertEqual(updated.avatar_source, "custom")
        self.assertEqual(updated.avatar_file_id, file_record.id)
        self.assertEqual(updated.version, self.agent.version + 1)
        # 立即生效不改变发布状态
        self.assertEqual(updated.publication_status, self.agent.publication_status)
        # 业务关系从未绑定变为归属当前智能体
        relation = ManagedFileBusinessRelation.objects.get(
            file=file_record, business_type=BUSINESS_TYPE_CLINICAL_AGENT_AVATAR
        )
        self.assertEqual(relation.business_id, str(self.agent.id))

    def test_switch_back_to_doctor_clears_file_and_keeps_history(self):
        file_record = make_avatar_file(self.hospital, self.user)
        updated = set_agent_avatar(
            agent_id=self.agent.id,
            avatar_source="custom",
            avatar_file_id=file_record.id,
            version=self.agent.version,
        )
        updated = set_agent_avatar(
            agent_id=self.agent.id,
            avatar_source="doctor",
            avatar_file_id=None,
            version=updated.version,
        )
        self.assertEqual(updated.avatar_source, "doctor")
        self.assertIsNone(updated.avatar_file_id)
        # 旧专属文件永久保留：未软删除、业务关系保留
        file_record.refresh_from_db()
        self.assertFalse(file_record.is_deleted)
        self.assertTrue(
            ManagedFileBusinessRelation.objects.filter(
                file=file_record, business_type=BUSINESS_TYPE_CLINICAL_AGENT_AVATAR
            ).exists()
        )

    def test_version_conflict_rejected(self):
        file_record = make_avatar_file(self.hospital, self.user)
        with self.assertRaises(HospitalCareError) as ctx:
            set_agent_avatar(
                agent_id=self.agent.id,
                avatar_source="custom",
                avatar_file_id=file_record.id,
                version=self.agent.version + 99,
            )
        self.assertEqual(ctx.exception.error_code, "AGENT_VERSION_CONFLICT")
        # 冲突后文件保持未绑定，线上头像不变
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.avatar_source, "doctor")

    def test_invalid_source_rejected(self):
        with self.assertRaises(HospitalCareError) as ctx:
            set_agent_avatar(
                agent_id=self.agent.id,
                avatar_source="robot",
                avatar_file_id=None,
                version=self.agent.version,
            )
        self.assertEqual(ctx.exception.error_code, "AVATAR_SOURCE_INVALID")


@override_settings(**OSS_SETTINGS)
class AgentAvatarPresenterTests(TestCase):
    def setUp(self):
        self.user = make_user("avatar-presenter")
        self.hospital = make_hospital(code="AVP-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)

    def test_public_payload_includes_avatar_fields_without_internal_leak(self):
        payload = agent_public(self.agent)
        self.assertEqual(payload["avatar_source"], "doctor")
        self.assertEqual(payload["avatar_version"], "default:v1")
        self.assertNotIn("avatar_file_id", payload)
        self.assertNotIn("object_key", str(payload))

    def test_internal_payload_includes_file_id_and_version(self):
        payload = agent_public(self.agent, include_internal=True)
        self.assertIn("avatar_file_id", payload)
        self.assertIn("version", payload)

    def test_agent_list_no_n_plus_one(self):
        file_record = make_avatar_file(self.hospital, self.user)
        self.doctor.avatar_file = file_record
        self.doctor.save(update_fields=["avatar_file"])
        for index in range(3):
            doctor = make_doctor(self.hospital, display_name=f"医生{index}")
            doctor.avatar_file = file_record
            doctor.save(update_fields=["avatar_file"])
            make_agent(self.hospital, doctor, self.department)

        from hospital_care.selectors import backoffice_hospital_catalog as catalog

        agents = list(catalog.hospital_agents(self.hospital.id))
        self.assertGreaterEqual(len(agents), 3)
        with self.assertNumQueries(0):  # 头像相关字段已通过 select_related 预取
            for agent in agents:
                payload = agent_public(agent)
                self.assertIn("avatar_url", payload)


@override_settings(**OSS_SETTINGS)
class AgentCreateWithAvatarTests(TestCase):
    def setUp(self):
        self.admin = make_user("avatar-create-admin", is_staff=True, is_superuser=True)
        self.request = DummyRequest(self.admin)
        self.hospital = make_hospital(code="AVN-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department, display_name="王医生")
        make_provider()
        from ai_config.models import AIModelCatalog

        AIModelCatalog.objects.get_or_create(
            name="hospital-care-test-model",
            defaults={"display_name": "Test Model", "company": "test", "is_active": True},
        )

    def _payload(self, **overrides):
        data = {
            "doctor_id": self.doctor.id,
            "department_id": self.department.id,
            "name": "王医生 AI 助手",
            "binding": {"model": "hospital-care-test-model"},
        }
        data.update(overrides)
        return data

    def test_create_defaults_to_doctor_source(self):
        agent = create_clinical_agent(request=self.request, hospital_id=self.hospital.id, payload=self._payload())
        self.assertEqual(agent.avatar_source, "doctor")
        self.assertIsNone(agent.avatar_file_id)

    def test_create_with_custom_avatar_binds_relation(self):
        file_record = make_avatar_file(self.hospital, self.admin)
        agent = create_clinical_agent(
            request=self.request,
            hospital_id=self.hospital.id,
            payload=self._payload(avatar_source="custom", avatar_file_id=file_record.id),
        )
        agent.refresh_from_db()
        self.assertEqual(agent.avatar_source, "custom")
        self.assertEqual(agent.avatar_file_id, file_record.id)
        relation = ManagedFileBusinessRelation.objects.get(
            file=file_record, business_type=BUSINESS_TYPE_CLINICAL_AGENT_AVATAR
        )
        self.assertEqual(relation.business_id, str(agent.id))

    def test_create_with_foreign_file_rolls_back(self):
        other = make_hospital(code="AVN-H2")
        file_record = make_avatar_file(other, self.admin)
        with self.assertRaises(HospitalCareError) as ctx:
            create_clinical_agent(
                request=self.request,
                hospital_id=self.hospital.id,
                payload=self._payload(avatar_source="custom", avatar_file_id=file_record.id),
            )
        self.assertEqual(ctx.exception.error_code, "AVATAR_FILE_FORBIDDEN")
        self.assertEqual(ClinicalAgentProfile.objects.filter(hospital=self.hospital).count(), 0)
        # 创建失败不删除文件
        file_record.refresh_from_db()
        self.assertFalse(file_record.is_deleted)


@override_settings(**OSS_SETTINGS)
class ConversationAvatarTests(TestCase):
    """会话内消息 sender 与简介卡的智能体头像。"""

    def setUp(self):
        from chat_sync.models import ChatThread

        self.user = make_user("conv-avatar-user")
        self.owner = make_user("conv-avatar-owner")
        self.hospital = make_hospital(code="CAV-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.thread = ChatThread.objects.create(user=self.user, title="头像会话")

    def _make_ai_message(self):
        import uuid as uuid_module
        from datetime import datetime, timezone

        from chat_sync.models import ChatMessage, ChatMessageBlock
        from hospital_care.models import ChatMessageAttribution

        message = ChatMessage.objects.create(
            user=self.user,
            thread=self.thread,
            role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid_module.uuid4(),
            server_message_id=str(uuid_module.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        ChatMessageBlock.objects.create(
            id=uuid_module.uuid4(),
            user=self.user,
            thread=self.thread,
            message=message,
            kind="text",
            status=ChatMessageBlock.Status.READY,
            revision=1,
            order_key=1000,
            node_role="timeline",
            payload={"text": {"_0": "您好"}},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        ChatMessageAttribution.objects.create(
            message=message,
            actor_type=ChatMessageAttribution.ActorType.AI_AGENT,
            agent=self.agent,
            display_name_snapshot=self.agent.name,
            source=ChatMessageAttribution.Source.AI_RUNTIME,
        )
        return message

    def test_ai_agent_sender_includes_doctor_avatar_when_reusing(self):
        from chat_sync.views import _to_payload

        doctor_file = make_avatar_file(self.hospital, self.owner)
        self.doctor.avatar_file = doctor_file
        self.doctor.save(update_fields=["avatar_file"])
        message = self._make_ai_message()

        sender = _to_payload(message)["sender"]
        self.assertEqual(sender["actor_type"], "ai_agent")
        self.assertIn(str(doctor_file.file_uuid), sender["avatar_url"])

    def test_ai_agent_sender_includes_custom_avatar(self):
        from chat_sync.views import _to_payload

        custom_file = make_avatar_file(self.hospital, self.owner)
        self.agent.avatar_source = ClinicalAgentProfile.AvatarSource.CUSTOM
        self.agent.avatar_file = custom_file
        self.agent.save(update_fields=["avatar_source", "avatar_file"])
        message = self._make_ai_message()

        sender = _to_payload(message)["sender"]
        self.assertIn(str(custom_file.file_uuid), sender["avatar_url"])

    def test_ai_agent_sender_avatar_none_when_no_avatar(self):
        from chat_sync.views import _to_payload

        message = self._make_ai_message()
        sender = _to_payload(message)["sender"]
        # 无医生/专属头像时落到统一 AI 默认头像（由测试 settings 配置）
        self.assertEqual(sender["avatar_url"], "https://cdn.test/default-avatar.png")

    def test_intro_card_includes_agent_avatar(self):
        from hospital_care.services.conversation_service import _doctor_intro_snapshot

        doctor_file = make_avatar_file(self.hospital, self.owner)
        self.doctor.avatar_file = doctor_file
        self.doctor.save(update_fields=["avatar_file"])
        self.agent.refresh_from_db()

        snapshot = _doctor_intro_snapshot(self.agent)
        self.assertIn(str(doctor_file.file_uuid), snapshot["agent"]["avatar_url"])
        self.assertIn(str(doctor_file.file_uuid), snapshot["doctor"]["avatar_url"])


@override_settings(**OSS_SETTINGS)
class DoctorAvatarUpdateTests(TestCase):
    def setUp(self):
        self.admin = make_user("doctor-avatar-admin", is_staff=True, is_superuser=True)
        self.request = DummyRequest(self.admin)
        self.hospital = make_hospital(code="DAV-H")
        self.other_hospital = make_hospital(code="DAV-H2")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)

    def _make_doctor_avatar(self, hospital=None):
        from file_manager.constants import DOCTOR_AVATAR_KEY_TEMPLATE

        file_uuid = uuid.uuid4()
        target_hospital = hospital or self.hospital
        record = ManagedFile.objects.create(
            user=self.admin,
            file_uuid=file_uuid,
            original_name="doctor.webp",
            mime_type="image/webp",
            file_size=100,
            object_key=DOCTOR_AVATAR_KEY_TEMPLATE.format(hospital_id=target_hospital.id, file_uuid=file_uuid),
        )
        bind_file_to_business(self.admin, record, "doctor_avatar_upload", "")
        return record

    def test_update_doctor_with_valid_avatar(self):
        from hospital_care.services.hospital_admin_service import update_doctor

        record = self._make_doctor_avatar()
        doctor = update_doctor(request=self.request, doctor_id=self.doctor.id, payload={"avatar_file_id": record.id})
        self.assertEqual(doctor.avatar_file_id, record.id)

    def test_update_doctor_clear_avatar(self):
        from hospital_care.services.hospital_admin_service import update_doctor

        record = self._make_doctor_avatar()
        self.doctor.avatar_file = record
        self.doctor.save(update_fields=["avatar_file"])
        doctor = update_doctor(request=self.request, doctor_id=self.doctor.id, payload={"avatar_file_id": None})
        self.assertIsNone(doctor.avatar_file_id)

    def test_update_doctor_missing_file_rejected(self):
        from hospital_care.services.hospital_admin_service import update_doctor

        with self.assertRaises(HospitalCareError) as ctx:
            update_doctor(request=self.request, doctor_id=self.doctor.id, payload={"avatar_file_id": 999999})
        self.assertEqual(ctx.exception.error_code, "AVATAR_FILE_NOT_FOUND")

    def test_update_doctor_non_image_rejected(self):
        from hospital_care.services.hospital_admin_service import update_doctor

        record = ManagedFile.objects.create(
            user=self.admin, original_name="a.pdf", mime_type="application/pdf", file_size=10, object_key="x/y.pdf"
        )
        with self.assertRaises(HospitalCareError) as ctx:
            update_doctor(request=self.request, doctor_id=self.doctor.id, payload={"avatar_file_id": record.id})
        self.assertEqual(ctx.exception.error_code, "AVATAR_FILE_FORBIDDEN")

    def test_update_doctor_cross_hospital_managed_key_rejected(self):
        from hospital_care.services.hospital_admin_service import update_doctor

        record = self._make_doctor_avatar(hospital=self.other_hospital)
        with self.assertRaises(HospitalCareError) as ctx:
            update_doctor(request=self.request, doctor_id=self.doctor.id, payload={"avatar_file_id": record.id})
        self.assertEqual(ctx.exception.error_code, "AVATAR_FILE_FORBIDDEN")


@override_settings(**OSS_SETTINGS)
class AgentAvatarApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user("avatar-api-admin", is_staff=True, is_superuser=True)
        self.staff_user = make_user("avatar-api-staff")
        self.hospital = make_hospital(code="AVA-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.url = f"/api/admin/v1/hospital-care/agents/{self.agent.id}/avatar/"

    def test_unauthenticated_rejected(self):
        response = self.client.patch(
            self.url,
            {"avatar_source": "doctor", "avatar_file_id": None, "version": self.agent.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ava-anon",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_staff_without_permission_rejected(self):
        self.client.force_authenticate(self.staff_user)
        response = self.client.patch(
            self.url,
            {"avatar_source": "doctor", "avatar_file_id": None, "version": self.agent.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ava-staff",
        )
        self.assertEqual(response.status_code, 403)

    def test_set_custom_avatar_via_api(self):
        self.client.force_authenticate(self.admin)
        file_record = make_avatar_file(self.hospital, self.admin)
        response = self.client.patch(
            self.url,
            {"avatar_source": "custom", "avatar_file_id": file_record.id, "version": self.agent.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ava-custom",
        )
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(data["avatar_source"], "custom")
        self.assertEqual(data["avatar_file_id"], file_record.id)
        self.assertEqual(data["version"], self.agent.version + 1)
        self.assertTrue(data["avatar_version"].startswith("custom:"))

    def test_idempotent_replay_does_not_double_increment(self):
        self.client.force_authenticate(self.admin)
        payload = {"avatar_source": "doctor", "avatar_file_id": None, "version": self.agent.version}
        first = self.client.patch(self.url, payload, format="json", HTTP_IDEMPOTENCY_KEY="ava-replay")
        second = self.client.patch(self.url, payload, format="json", HTTP_IDEMPOTENCY_KEY="ava-replay")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(first.data["data"]["version"], second.data["data"]["version"])
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.version, first.data["data"]["version"])

    def test_version_conflict_returns_latest_version(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            self.url,
            {"avatar_source": "doctor", "avatar_file_id": None, "version": self.agent.version + 5},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ava-conflict",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "AGENT_VERSION_CONFLICT")
        self.assertEqual(response.data["data"]["version"], self.agent.version)

    def test_custom_without_file_id_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            self.url,
            {"avatar_source": "custom", "version": self.agent.version},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ava-nofile",
        )
        self.assertEqual(response.status_code, 400)
