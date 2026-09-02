from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ai_config.models import AIModelCatalog, AIScenarioModelBinding, IdentityKind, ScenarioKey
from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeBaseKind
from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from medical.models import Member, UserMemberBinding

from hospital_care.models import (
    ChatMessageAttribution,
    ClinicalAgentKnowledgeBinding,
    ClinicalAgentProfile,
    ClinicalConversationBinding,
    DoctorDepartmentMembership,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalStaffMembership,
)

User = get_user_model()

HOSPITAL_CODE = "TCZY-001"
SERVICE_USERNAME = "hospital_care_kb_owner"
ADMIN_USERNAME = "hospital_demo_admin"
DOCTOR_SPECS = [
    ("hospital_demo_doctor_zhang", "张医生", "主任医师", "CARD", "张医生 AI 助手", True),
    ("hospital_demo_doctor_li", "李医生", "副主任医师", "DERM", "李医生 AI 助手", False),
    ("hospital_demo_doctor_wang", "王医生", "主治医师", "PEDI", "王医生 AI 助手", False),
]
DEPARTMENTS = [
    ("CARD", "心内科", "心血管内科"),
    ("DERM", "皮肤科", "皮肤性病科"),
    ("PEDI", "儿科", "儿科门诊"),
]


class Command(BaseCommand):
    help = "Idempotently seed fictional hospital_care demo data. All records are synthetic."

    def handle(self, *args, **options):
        with transaction.atomic():
            hospital = self._hospital()
            departments = self._departments(hospital)
            admin_user = self._user(ADMIN_USERNAME, is_staff=True)
            self._membership(hospital, admin_user, HospitalStaffMembership.Role.HOSPITAL_ADMIN)
            kb_owner = self._user(SERVICE_USERNAME)
            knowledge_base = self._knowledge_base(kb_owner)
            binding = self._scenario_binding()
            doctors = []
            agents = []
            for username, display_name, title, dept_code, agent_name, published in DOCTOR_SPECS:
                user = self._user(username)
                membership = self._membership(hospital, user, HospitalStaffMembership.Role.DOCTOR, status=HospitalStaffMembership.Status.ACTIVE)
                doctor = self._doctor(membership, display_name, title)
                DoctorDepartmentMembership.objects.get_or_create(
                    doctor=doctor,
                    department=departments[dept_code],
                    defaults={"is_primary": True},
                )
                agent = self._agent(hospital, doctor, departments[dept_code], binding, agent_name, published)
                if published:
                    ClinicalAgentKnowledgeBinding.objects.get_or_create(
                        agent=agent,
                        knowledge_base=knowledge_base,
                        defaults={"usage_scope": ClinicalAgentKnowledgeBinding.UsageScope.HOSPITAL, "status": ClinicalAgentKnowledgeBinding.Status.ACTIVE},
                    )
                doctors.append(doctor)
                agents.append(agent)
            patients = self._patients()
            self._conversations(hospital, departments, doctors, agents, patients)
        self.stdout.write(self.style.SUCCESS(f"Seeded demo hospital {hospital.code}"))

    def _user(self, username: str, is_staff: bool = False):
        user, _ = User.objects.get_or_create(username=username, defaults={"email": f"{username}@demo.invalid", "is_staff": is_staff})
        if not user.has_usable_password():
            user.set_password("demo-hospital-care")
            user.save(update_fields=["password"])
        return user

    def _hospital(self) -> Hospital:
        hospital, created = Hospital.objects.get_or_create(
            code=HOSPITAL_CODE,
            defaults={
                "name": "天长市中医院",
                "short_name": "天长中医院",
                "grade": "三甲",
                "province_code": "340000",
                "city_code": "341100",
                "district_code": "341181",
                "address": "安徽省滁州市天长市演示路 1 号",
                "service_phone": "0550-0000000",
                "service_mode": Hospital.ServiceMode.DEMO,
                "status": Hospital.Status.ACTIVE,
                "introduction": "虚构演示医院，仅用于产品演示。",
            },
        )
        if not created and hospital.status != Hospital.Status.ACTIVE:
            hospital.status = Hospital.Status.ACTIVE
            hospital.save(update_fields=["status", "updated_at"])
        return hospital

    def _departments(self, hospital: Hospital) -> dict[str, HospitalDepartment]:
        result = {}
        for index, (code, name, description) in enumerate(DEPARTMENTS):
            department, _ = HospitalDepartment.objects.get_or_create(
                hospital=hospital,
                code=code,
                defaults={"name": name, "short_name": name, "description": description, "sort_order": index, "status": HospitalDepartment.Status.ACTIVE},
            )
            result[code] = department
        return result

    def _membership(self, hospital, user, role, status=HospitalStaffMembership.Status.ACTIVE):
        membership, _ = HospitalStaffMembership.objects.get_or_create(
            hospital=hospital,
            user=user,
            defaults={"role": role, "status": status, "joined_at": timezone.now(), "employee_no": f"E{user.id:05d}"},
        )
        return membership

    def _doctor(self, membership, display_name, title) -> DoctorProfile:
        doctor, _ = DoctorProfile.objects.get_or_create(
            staff_membership=membership,
            defaults={
                "display_name": display_name,
                "title": title,
                "specialties": ["演示专科"],
                "introduction": "虚构医生档案，仅用于产品演示。",
                "license_status": DoctorProfile.LicenseStatus.VERIFIED,
                "profile_status": DoctorProfile.ProfileStatus.ACTIVE,
            },
        )
        return doctor

    def _knowledge_base(self, owner) -> KnowledgeBase:
        knowledge_base, _ = KnowledgeBase.objects.get_or_create(
            user=owner,
            name="心内科患者教育库 Demo",
            defaults={"kind": KnowledgeBaseKind.SYSTEM, "is_default": False},
        )
        return knowledge_base

    def _scenario_binding(self) -> AIScenarioModelBinding:
        model, _ = AIModelCatalog.objects.get_or_create(
            name="hospital-care-demo-model",
            defaults={"display_name": "Hospital Care Demo Model", "company": "demo", "is_active": True},
        )
        binding, _ = AIScenarioModelBinding.objects.get_or_create(
            scenario=ScenarioKey.CHAT,
            identity=IdentityKind.AGENT,
            model=model,
            defaults={"display_name": "医院演示智能体", "is_active": True, "is_default": False},
        )
        return binding

    def _agent(self, hospital, doctor, department, scenario, name, published) -> ClinicalAgentProfile:
        agent, _ = ClinicalAgentProfile.objects.get_or_create(
            doctor=doctor,
            department=department,
            defaults={
                "hospital": hospital,
                "scenario_binding": scenario,
                "name": name,
                "public_summary": "虚构医生智能体，仅用于产品演示。",
                "greeting": "您好，我是演示智能助手，不能替代面诊。",
                "service_boundary": "健康信息与就医指导，不提供确诊或处方。",
                "publication_status": ClinicalAgentProfile.PublicationStatus.PUBLISHED if published else ClinicalAgentProfile.PublicationStatus.DRAFT,
                "published_at": timezone.now() if published else None,
            },
        )
        return agent

    def _patients(self):
        items = []
        for username, member_name in (("hospital_demo_patient_a", "演示患者 03"), ("hospital_demo_patient_b", "演示患者 07")):
            user = self._user(username)
            member, _ = Member.all_objects.get_or_create(user=user, name=member_name, defaults={"gender": Member.Gender.UNKNOWN, "is_primary": True})
            UserMemberBinding.objects.get_or_create(user=user, member=member, defaults={"relationship": "self", "role": UserMemberBinding.Role.OWNER})
            items.append((user, member))
        return items

    def _conversations(self, hospital, departments, doctors, agents, patients):
        published_agent = next(agent for agent in agents if agent.publication_status == ClinicalAgentProfile.PublicationStatus.PUBLISHED)
        doctor = published_agent.doctor
        specs = [
            ("demo-normal", patients[0], ClinicalConversationBinding.ServiceStatus.AI_ACTIVE, ClinicalConversationBinding.AttentionLevel.NORMAL, ClinicalConversationBinding.RiskSignalLevel.LOW, False),
            ("demo-priority", patients[0], ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED, ClinicalConversationBinding.AttentionLevel.PRIORITY, ClinicalConversationBinding.RiskSignalLevel.HIGH, True),
            ("demo-ended", patients[1], ClinicalConversationBinding.ServiceStatus.ENDED, ClinicalConversationBinding.AttentionLevel.NORMAL, ClinicalConversationBinding.RiskSignalLevel.MEDIUM, False),
            ("demo-pending", patients[1], ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR, ClinicalConversationBinding.AttentionLevel.FOLLOW_UP, ClinicalConversationBinding.RiskSignalLevel.MEDIUM, False),
        ]
        now = timezone.now()
        for key, (user, member), status, attention, risk, with_doctor_msg in specs:
            thread_id = uuid.uuid5(uuid.NAMESPACE_URL, f"hospital-care-demo:{key}")
            thread, _ = ChatThread.objects.get_or_create(
                id=thread_id,
                defaults={"user": user, "member_id": member.id, "title": f"{member.name} · {published_agent.name}"},
            )
            if thread.user_id != user.id:
                continue
            binding, _ = ClinicalConversationBinding.objects.get_or_create(
                thread=thread,
                defaults={
                    "hospital": hospital,
                    "department": published_agent.department,
                    "doctor": doctor,
                    "agent": published_agent,
                    "service_status": status,
                    "doctor_attention_level": attention,
                    "risk_signal_level": risk,
                    "assigned_at": now - timedelta(hours=1),
                    "doctor_joined_at": now if status == ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED else None,
                    "ended_at": now if status == ClinicalConversationBinding.ServiceStatus.ENDED else None,
                    "end_reason": "已完成咨询" if status == ClinicalConversationBinding.ServiceStatus.ENDED else "",
                },
            )
            self._ensure_message(thread, ChatMessage.Role.ASSISTANT, ChatMessageAttribution.ActorType.AI_AGENT, published_agent.name, "您描述的情况需要进一步确认。", agent=published_agent)
            if with_doctor_msg:
                self._ensure_message(thread, ChatMessage.Role.ASSISTANT, ChatMessageAttribution.ActorType.DOCTOR, f"{doctor.display_name} · 真人医生", "请立即停止活动并呼叫 120。", doctor=doctor, user=doctor.staff_membership.user)

        suspended, _ = Hospital.objects.get_or_create(
            code="DEMO-SUSPENDED",
            defaults={
                "name": "演示暂停医院",
                "address": "演示地址",
                "province_code": "340000",
                "city_code": "340100",
                "service_mode": Hospital.ServiceMode.DEMO,
                "status": Hospital.Status.SUSPENDED,
            },
        )
        if suspended.status != Hospital.Status.SUSPENDED:
            suspended.status = Hospital.Status.SUSPENDED
            suspended.save(update_fields=["status", "updated_at"])

    def _ensure_message(self, thread, role, actor_type, display_name, text, agent=None, doctor=None, user=None):
        existing = ChatMessageAttribution.objects.filter(message__thread=thread, actor_type=actor_type, display_name_snapshot=display_name).first()
        if existing:
            return existing.message
        now = timezone.now()
        message = ChatMessage.objects.create(
            user=thread.user,
            thread=thread,
            role=role,
            client_message_id=uuid.uuid4(),
            server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=now,
        )
        ChatMessageBlock.objects.create(
            id=uuid.uuid4(),
            user=thread.user,
            thread=thread,
            message=message,
            kind="text",
            status=ChatMessageBlock.Status.READY,
            revision=1,
            order_key=1000,
            node_role="timeline",
            payload={"text": {"_0": text}},
            created_at=now,
            updated_at=now,
        )
        ChatMessageAttribution.objects.create(
            message=message,
            actor_type=actor_type,
            actor_user=user,
            doctor=doctor,
            agent=agent,
            display_name_snapshot=display_name,
            source=ChatMessageAttribution.Source.SYSTEM if actor_type == ChatMessageAttribution.ActorType.AI_AGENT else ChatMessageAttribution.Source.DOCTOR_CONSOLE,
        )
        return message
