from __future__ import annotations

import uuid
from pathlib import PurePosixPath
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ai_config.models import AIScenarioModelBinding, IdentityKind, ScenarioKey
from file_manager.business_relations import bind_file_to_business
from file_manager.models import ManagedFile
from hospital_care.data.tianchang_people_hospital import DEPARTMENTS, DOCTORS, HOSPITAL
from hospital_care.models import (
    ClinicalAgentProfile,
    DoctorDepartmentMembership,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalStaffMembership,
)

User = get_user_model()

ADMIN_USERNAME = "tcsyy_admin"
SERVICE_USERNAME = "tcsyy_service"
DEFAULT_PASSWORD = "tcsyy-demo"


class Command(BaseCommand):
    help = "幂等写入天长市人民医院、内三科官网公开医生及一医生一智能体。"

    def add_arguments(self, parser):
        parser.add_argument("--code", default=HOSPITAL["code"])
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--activate", action="store_true")

    def handle(self, *args, **options):
        with transaction.atomic():
            hospital = self._hospital(options["code"])
            service_user = self._user(SERVICE_USERNAME, "天长市人民医院服务账号", options["password"])
            self._hospital_logo(hospital, service_user)
            departments = self._departments(hospital)
            admin = self._user(ADMIN_USERNAME, "医院管理员", options["password"], is_staff=True)
            self._membership(hospital, admin, HospitalStaffMembership.Role.HOSPITAL_ADMIN, "A0001")
            template = self._template_binding()
            position = self._next_position()

            for index, item in enumerate(DOCTORS, start=1):
                user = self._user(
                    "tcsyy_doc_{0}".format(item["source_id"]),
                    item["name"],
                    options["password"],
                )
                membership = self._membership(
                    hospital,
                    user,
                    HospitalStaffMembership.Role.DOCTOR,
                    "D{0}".format(item["source_id"]),
                )
                avatar = self._external_image(user, item["avatar_url"])
                doctor = self._doctor(membership, item, avatar)
                department = departments["CLIN_NEURO_3"]
                DoctorDepartmentMembership.objects.update_or_create(
                    doctor=doctor,
                    department=department,
                    defaults={"is_primary": True, "sort_order": 0, "status": DoctorDepartmentMembership.Status.ACTIVE},
                )
                self._agent(hospital, doctor, department, item, template, position + index)
                bind_file_to_business(user, avatar, "doctor_avatar", str(doctor.id))

            if options["activate"] and hospital.status != Hospital.Status.ACTIVE:
                hospital.status = Hospital.Status.ACTIVE
                hospital.version += 1
                hospital.save(update_fields=["status", "version", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            "医院 {0}({1}) 已写入：科室 {2}，医生 {3}，医生头像 {3}，医生智能体 {3}。".format(
                hospital.name, hospital.code, len(DEPARTMENTS), len(DOCTORS)
            )
        ))
        self.stdout.write("智能体统一复用医生头像；头像保存为官网公开地址。")

    def _hospital(self, code: str) -> Hospital:
        defaults = {key: value for key, value in HOSPITAL.items() if key not in {"code", "logo_url"}}
        defaults["status"] = Hospital.Status.DRAFT
        hospital, _ = Hospital.objects.get_or_create(code=code, defaults=defaults)
        changed = []
        for field, value in defaults.items():
            if getattr(hospital, field) != value:
                setattr(hospital, field, value)
                changed.append(field)
        if changed:
            hospital.version += 1
            hospital.save(update_fields=[*changed, "version", "updated_at"])
        return hospital

    def _user(self, username: str, first_name: str, password: str, is_staff: bool = False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@tcsyy.demo", "first_name": first_name, "is_staff": is_staff},
        )
        changed = created
        if not user.has_usable_password():
            user.set_password(password)
            changed = True
        if user.first_name != first_name or user.is_staff != is_staff:
            user.first_name = first_name
            user.is_staff = is_staff
            changed = True
        if changed:
            user.save()
        return user

    def _hospital_logo(self, hospital, owner):
        logo = self._external_image(owner, HOSPITAL["logo_url"], "hospital_logo")
        if hospital.logo_file_id != logo.id:
            hospital.logo_file = logo
            hospital.knowledge_service_user = owner
            hospital.version += 1
            hospital.save(update_fields=["logo_file", "knowledge_service_user", "version", "updated_at"])
        bind_file_to_business(owner, logo, "hospital_logo", str(hospital.id))

    def _departments(self, hospital):
        result = {}
        for index, item in enumerate(DEPARTMENTS):
            department, _ = HospitalDepartment.objects.update_or_create(
                hospital=hospital,
                code=item["code"],
                defaults={
                    "parent": None,
                    "name": item["name"],
                    "short_name": item["short_name"],
                    "description": item["description"],
                    "sort_order": index,
                    "status": HospitalDepartment.Status.ACTIVE,
                },
            )
            result[item["code"]] = department
        return result

    def _membership(self, hospital, user, role, employee_no):
        membership, _ = HospitalStaffMembership.objects.update_or_create(
            hospital=hospital,
            user=user,
            defaults={
                "role": role,
                "status": HospitalStaffMembership.Status.ACTIVE,
                "employee_no": employee_no,
                "joined_at": timezone.now(),
            },
        )
        return membership

    def _doctor(self, membership, item, avatar):
        return DoctorProfile.objects.update_or_create(
            staff_membership=membership,
            defaults={
                "display_name": item["name"],
                "title": item["title"],
                "specialties": item["specialties"],
                "introduction": f'{item["introduction"]}（资料页：{item["profile_url"]}）',
                "avatar_file": avatar,
                "license_status": DoctorProfile.LicenseStatus.VERIFIED,
                "profile_status": DoctorProfile.ProfileStatus.ACTIVE,
            },
        )[0]

    def _template_binding(self):
        binding = AIScenarioModelBinding.objects.select_related("model").filter(
            scenario=ScenarioKey.CHAT,
            is_active=True,
            model__is_active=True,
        ).order_by("-is_default", "position", "id").first()
        if binding is None:
            raise CommandError("没有可用的 chat 场景模型绑定，无法创建医生智能体")
        return binding

    def _next_position(self):
        return int(
            AIScenarioModelBinding.objects.filter(
                scenario=ScenarioKey.CHAT,
                identity=IdentityKind.AGENT,
            ).order_by("-position").values_list("position", flat=True).first() or 0
        )

    def _agent(self, hospital, doctor, department, item, template, position):
        binding = None
        agent = ClinicalAgentProfile.objects.filter(hospital=hospital, doctor=doctor).order_by("created_at", "id").first()
        if agent is not None:
            binding = agent.scenario_binding
        if binding is None:
            binding = AIScenarioModelBinding.objects.create(
                scenario=ScenarioKey.CHAT,
                identity=IdentityKind.AGENT,
                model=template.model,
                display_name=f'{item["name"]}医生智能体',
                temperature=template.temperature,
                max_tokens=template.max_tokens,
                position=position,
                is_active=True,
                system_provision=self._system_provision(item),
                brief_description=f'内三科 · {item["introduction"]}',
                ai_tool_scenarios=list(template.ai_tool_scenarios or []),
                server_tool_scenarios=list(template.server_tool_scenarios or []),
                related_task_codes=list(template.related_task_codes or []),
            )
        else:
            binding.model = template.model
            binding.display_name = f'{item["name"]}医生智能体'
            binding.temperature = template.temperature
            binding.max_tokens = template.max_tokens
            binding.position = position
            binding.is_active = True
            binding.system_provision = self._system_provision(item)
            binding.brief_description = f'内三科 · {item["introduction"]}'
            binding.ai_tool_scenarios = list(template.ai_tool_scenarios or [])
            binding.server_tool_scenarios = list(template.server_tool_scenarios or [])
            binding.related_task_codes = list(template.related_task_codes or [])
            binding.save()
        defaults = {
            "department": department,
            "scenario_binding": binding,
            "name": f'{item["name"]}医生智能体',
            "public_summary": item["introduction"],
            "greeting": f'您好，我是天长市人民医院内三科{item["name"]}医生智能体。',
            "service_boundary": "提供神经内科健康科普与就医指导，不替代面诊，不作确定诊断或开具处方。",
            "publication_status": ClinicalAgentProfile.PublicationStatus.PUBLISHED,
            "avatar_source": ClinicalAgentProfile.AvatarSource.DOCTOR,
            "avatar_file": None,
            "published_at": timezone.now(),
        }
        if agent is None:
            ClinicalAgentProfile.objects.create(hospital=hospital, doctor=doctor, **defaults)
        else:
            for field, value in defaults.items():
                setattr(agent, field, value)
            agent.version += 1
            agent.save()

    def _system_provision(self, item):
        return (
            f'你是天长市人民医院内三科{item["name"]}医生的院内智能体。'
            f'公开职称为{item["title"]}，擅长：{"、".join(item["specialties"])}。'
            "只提供健康科普和就医准备建议，不声称已面诊，不作确定诊断或处方；发现急危重症信号时建议立即线下就医或拨打120。"
        )

    def _external_image(self, owner, url, business_type="doctor_avatar"):
        file_uuid = uuid.uuid5(uuid.NAMESPACE_URL, url)
        filename = PurePosixPath(urlparse(url).path).name or f"{file_uuid}.jpg"
        extension = PurePosixPath(filename).suffix.lower().lstrip(".") or "jpg"
        mime_type = "image/png" if extension == "png" else "image/jpeg"
        record, _ = ManagedFile.objects.update_or_create(
            file_uuid=file_uuid,
            defaults={
                "user": owner,
                "file_path": url,
                "original_name": filename,
                "file_ext": extension,
                "mime_type": mime_type,
                "file_size": 0,
                "is_public": True,
                "object_key": "",
                "storage_type": "external",
                "is_deleted": False,
                "deleted_at": None,
            },
        )
        bind_file_to_business(owner, record, business_type, "")
        return record

