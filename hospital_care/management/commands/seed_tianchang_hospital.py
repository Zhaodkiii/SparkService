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
from hospital_care.data.tianchang_public_staff import DEPARTMENTS, doctors_with_departments
from hospital_care.models import (
    ClinicalAgentProfile,
    DoctorDepartmentMembership,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalStaffMembership,
)

User = get_user_model()

DEFAULT_CODE = "000001"
DEFAULT_PASSWORD = "tcszyy-demo"
ADMIN_USERNAME = "tcszyy_admin"
SERVICE_USERNAME = "tcszyy_service"
OFFICIAL_LOGO_URL = "http://www.tcszyy.com/upload/images/2021/3/1854427526.png"

HOSPITAL_DEFAULTS = {
    "name": "天长市中医院",
    "short_name": "天长中医院",
    "grade": "三级中医医院",
    "province_code": "340000",
    "city_code": "341100",
    "district_code": "341181",
    "address": "安徽省滁州市天长市天宁大道222号",
    "service_phone": "0550-7046442",
    "emergency_phone": "120",
    "website_url": "http://www.tcszyy.com/",
    "registration_redirect_url": "",
    "service_mode": Hospital.ServiceMode.DEMO,
    "introduction": (
        "天长市中医院始建于1954年，1996年获批全国示范中医院，2018年晋升为三级中医医院。"
        "2024年5月医院新区竣工启用，新区占地133亩，总建筑面积15万平方米，规划床位1100张，"
        "开放床位850张。医院在岗职工810人，中高级职称人员近400人，开设30多个临床医技科室，"
        "设立专科专病门诊20个。以上资料来自医院官网2026年9月公开页面，仅用于产品演示。"
    ),
}

AGENT_SERVICE_BOUNDARY = (
    "提供医院、科室、医生公开信息以及健康科普和就医指导；"
    "不能替代执业医生面诊，不作确诊，不开具处方；出现急危重症信号时提示立即线下就医或拨打120。"
)


class Command(BaseCommand):
    help = (
        "幂等写入天长市中医院官网公开医院资料、30个科室节点、142位医生及其头像，"
        "并为每位医生创建一个已发布且复用医生头像的智能体。"
    )

    def add_arguments(self, parser):
        parser.add_argument("--code", default=DEFAULT_CODE, help="医院唯一编码，默认 000001")
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help="演示账号初始密码")
        parser.add_argument("--activate", action="store_true", help="将医院标为已启用")

    def handle(self, *args, **options):
        code = (options["code"] or DEFAULT_CODE).strip()
        password = options["password"]
        public_doctors = doctors_with_departments()
        with transaction.atomic():
            hospital = self._hospital(code)
            service_user = self._user(
                SERVICE_USERNAME,
                first_name="天长市中医院服务账号",
                password=password,
                is_staff=False,
            )
            self._configure_hospital_assets(hospital, service_user)
            departments = self._departments(hospital)
            admin = self._user(
                ADMIN_USERNAME,
                first_name="医院管理员",
                password=password,
                is_staff=True,
            )
            self._membership(
                hospital,
                admin,
                HospitalStaffMembership.Role.HOSPITAL_ADMIN,
                employee_no="A0001",
            )
            template_binding = self._template_binding()
            next_position = self._next_agent_position()
            doctor_count = 0
            agent_count = 0
            avatar_count = 0
            for index, item in enumerate(public_doctors, start=1):
                source_id = self._source_id(item)
                username = "tcszyy_doc_{0}".format(source_id)
                user = self._user(
                    username,
                    first_name=str(item["name"]),
                    password=password,
                    is_staff=False,
                )
                membership = self._membership(
                    hospital,
                    user,
                    HospitalStaffMembership.Role.DOCTOR,
                    employee_no="D{0}".format(source_id),
                )
                avatar_file = self._external_image(
                    owner=user,
                    url=str(item["avatar_url"]),
                    business_type="doctor_avatar",
                )
                doctor = self._doctor(membership, item, avatar_file)
                self._doctor_departments(
                    doctor=doctor,
                    department_codes=list(item["department_codes"]),
                    departments=departments,
                )
                agent = self._agent(
                    hospital=hospital,
                    doctor=doctor,
                    department=departments[str(item["department_code"])],
                    item=item,
                    template=template_binding,
                    position=next_position + index,
                )
                bind_file_to_business(
                    user,
                    avatar_file,
                    "doctor_avatar",
                    str(doctor.id),
                )
                doctor_count += 1
                agent_count += 1
                avatar_count += 1

            if options["activate"] and hospital.status != Hospital.Status.ACTIVE:
                hospital.status = Hospital.Status.ACTIVE
                hospital.version += 1
                hospital.save(update_fields=["status", "version", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                "医院 {0}({1}) 已写入：科室节点 {2}（含2个分类、28个科室），"
                "医生 {3}，医生头像 {4}，医生智能体 {5}。".format(
                    hospital.name,
                    hospital.code,
                    len(departments),
                    doctor_count,
                    avatar_count,
                    agent_count,
                )
            )
        )
        self.stdout.write(
            "头像直接引用医院官网公开地址；智能体统一 avatar_source=doctor，不复制医生头像文件。"
        )

    def _hospital(self, code: str) -> Hospital:
        hospital, created = Hospital.objects.get_or_create(
            code=code,
            defaults={**HOSPITAL_DEFAULTS, "status": Hospital.Status.DRAFT},
        )
        dirty = []
        for field, value in HOSPITAL_DEFAULTS.items():
            if getattr(hospital, field) != value:
                setattr(hospital, field, value)
                dirty.append(field)
        if dirty:
            hospital.version += 1
            hospital.save(update_fields=[*dirty, "version", "updated_at"])
        if created:
            self.stdout.write("已创建医院 {0}".format(code))
        else:
            self.stdout.write("已更新现有医院 {0} / {1}".format(code, hospital.name))
        return hospital

    def _configure_hospital_assets(self, hospital: Hospital, service_user):
        logo_file = self._external_image(
            owner=service_user,
            url=OFFICIAL_LOGO_URL,
            business_type="hospital_logo",
        )
        bind_file_to_business(
            service_user,
            logo_file,
            "hospital_logo",
            str(hospital.id),
        )
        dirty = []
        if hospital.knowledge_service_user_id != service_user.id:
            hospital.knowledge_service_user = service_user
            dirty.append("knowledge_service_user")
        if hospital.logo_file_id != logo_file.id:
            hospital.logo_file = logo_file
            dirty.append("logo_file")
        if dirty:
            hospital.version += 1
            hospital.save(update_fields=[*dirty, "version", "updated_at"])

    def _departments(self, hospital: Hospital) -> dict[str, HospitalDepartment]:
        result: dict[str, HospitalDepartment] = {}
        for index, (code, name, short_name, description, parent_code) in enumerate(DEPARTMENTS):
            if parent_code is not None:
                continue
            department, _ = HospitalDepartment.objects.update_or_create(
                hospital=hospital,
                code=code,
                defaults={
                    "parent": None,
                    "name": name,
                    "short_name": short_name,
                    "description": description,
                    "sort_order": index,
                    "status": HospitalDepartment.Status.ACTIVE,
                },
            )
            result[code] = department

        for index, (code, name, short_name, description, parent_code) in enumerate(DEPARTMENTS):
            if parent_code is None:
                continue
            department, _ = HospitalDepartment.objects.update_or_create(
                hospital=hospital,
                code=code,
                defaults={
                    "parent": result[parent_code],
                    "name": name,
                    "short_name": short_name,
                    "description": description,
                    "sort_order": index,
                    "status": HospitalDepartment.Status.ACTIVE,
                },
            )
            result[code] = department
        return result

    def _user(
        self,
        username: str,
        *,
        first_name: str,
        password: str,
        is_staff: bool,
    ):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": "{0}@tcszyy.demo".format(username),
                "first_name": first_name,
                "is_staff": is_staff,
            },
        )
        changed = created
        if created or not user.has_usable_password():
            user.set_password(password)
            changed = True
        if user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if user.is_staff != is_staff:
            user.is_staff = is_staff
            changed = True
        if changed:
            user.save()
        return user

    def _membership(self, hospital, user, role, *, employee_no: str):
        membership, _ = HospitalStaffMembership.objects.update_or_create(
            hospital=hospital,
            user=user,
            defaults={
                "role": role,
                "status": HospitalStaffMembership.Status.ACTIVE,
                "joined_at": timezone.now(),
                "employee_no": employee_no,
            },
        )
        return membership

    def _doctor(self, membership, item: dict[str, object], avatar_file: ManagedFile) -> DoctorProfile:
        doctor, _ = DoctorProfile.objects.update_or_create(
            staff_membership=membership,
            defaults={
                "display_name": str(item["name"]),
                "title": str(item["title"]),
                "specialties": list(item["department_codes"]),
                "introduction": (
                    "{0}（官网公开诊室：{1}；资料页：{2}）".format(
                        item["introduction"],
                        item["room"],
                        item["profile_url"],
                    )
                ),
                "avatar_file": avatar_file,
                "license_status": DoctorProfile.LicenseStatus.VERIFIED,
                "profile_status": DoctorProfile.ProfileStatus.ACTIVE,
            },
        )
        return doctor

    def _doctor_departments(
        self,
        *,
        doctor: DoctorProfile,
        department_codes: list[str],
        departments: dict[str, HospitalDepartment],
    ):
        for sort_order, code in enumerate(department_codes):
            DoctorDepartmentMembership.objects.update_or_create(
                doctor=doctor,
                department=departments[code],
                defaults={
                    "is_primary": sort_order == 0,
                    "sort_order": sort_order,
                    "status": DoctorDepartmentMembership.Status.ACTIVE,
                },
            )

    def _template_binding(self) -> AIScenarioModelBinding:
        binding = (
            AIScenarioModelBinding.objects.select_related("model")
            .filter(
                scenario=ScenarioKey.CHAT,
                is_active=True,
                model__is_active=True,
            )
            .order_by("-is_default", "position", "id")
            .first()
        )
        if binding is None:
            raise CommandError("没有可用的 chat 场景模型绑定，无法创建医生智能体")
        return binding

    def _next_agent_position(self) -> int:
        latest = (
            AIScenarioModelBinding.objects.filter(
                scenario=ScenarioKey.CHAT,
                identity=IdentityKind.AGENT,
            )
            .order_by("-position")
            .values_list("position", flat=True)
            .first()
        )
        return int(latest or 0)

    def _agent(
        self,
        *,
        hospital: Hospital,
        doctor: DoctorProfile,
        department: HospitalDepartment,
        item: dict[str, object],
        template: AIScenarioModelBinding,
        position: int,
    ) -> ClinicalAgentProfile:
        agent_name = "{0}医生智能体".format(item["name"])
        agent = (
            ClinicalAgentProfile.objects.filter(
                hospital=hospital,
                doctor=doctor,
            )
            .order_by("created_at", "id")
            .first()
        )
        if agent is None:
            binding = AIScenarioModelBinding.objects.create(
                scenario=ScenarioKey.CHAT,
                identity=IdentityKind.AGENT,
                model=template.model,
                display_name=agent_name,
                temperature=template.temperature,
                max_tokens=template.max_tokens,
                position=position,
                is_default=False,
                is_active=True,
                system_provision=self._system_provision(item, department),
                brief_description="{0} · {1}".format(department.name, item["introduction"]),
                ai_tool_scenarios=list(template.ai_tool_scenarios or []),
                server_tool_scenarios=list(template.server_tool_scenarios or []),
                related_task_codes=list(template.related_task_codes or []),
            )
            agent = ClinicalAgentProfile.objects.create(
                hospital=hospital,
                doctor=doctor,
                department=department,
                scenario_binding=binding,
                name=agent_name,
                public_summary=str(item["introduction"]),
                greeting=self._greeting(item, department),
                service_boundary=AGENT_SERVICE_BOUNDARY,
                publication_status=ClinicalAgentProfile.PublicationStatus.PUBLISHED,
                avatar_source=ClinicalAgentProfile.AvatarSource.DOCTOR,
                avatar_file=None,
                published_at=timezone.now(),
            )
            return agent

        binding = agent.scenario_binding
        binding.model = template.model
        binding.display_name = agent_name
        binding.temperature = template.temperature
        binding.max_tokens = template.max_tokens
        binding.position = position
        binding.is_default = False
        binding.is_active = True
        binding.system_provision = self._system_provision(item, department)
        binding.brief_description = "{0} · {1}".format(department.name, item["introduction"])
        binding.ai_tool_scenarios = list(template.ai_tool_scenarios or [])
        binding.server_tool_scenarios = list(template.server_tool_scenarios or [])
        binding.related_task_codes = list(template.related_task_codes or [])
        binding.save()

        agent.department = department
        agent.name = agent_name
        agent.public_summary = str(item["introduction"])
        agent.greeting = self._greeting(item, department)
        agent.service_boundary = AGENT_SERVICE_BOUNDARY
        agent.publication_status = ClinicalAgentProfile.PublicationStatus.PUBLISHED
        agent.avatar_source = ClinicalAgentProfile.AvatarSource.DOCTOR
        agent.avatar_file = None
        agent.published_at = agent.published_at or timezone.now()
        agent.version += 1
        agent.save()
        return agent

    def _system_provision(
        self,
        item: dict[str, object],
        department: HospitalDepartment,
    ) -> str:
        return (
            "你是天长市中医院{0}{1}医生的院内智能体。医生公开职称为{2}。"
            "医生公开擅长：{3}"
            "回答应优先围绕本科室健康科普、就医准备和风险分层；"
            "不得声称已完成面诊，不得作确定诊断或开具处方。"
            "发现急危重症信号时应明确建议立即线下就医或拨打120。"
        ).format(
            department.name,
            item["name"],
            item["title"],
            item["introduction"],
        )

    def _greeting(
        self,
        item: dict[str, object],
        department: HospitalDepartment,
    ) -> str:
        return (
            "您好，我是天长市中医院{0}{1}医生智能体。"
            "我可以结合{0}公开服务信息，为您提供健康科普和就医准备建议。"
        ).format(department.name, item["name"])

    def _source_id(self, item: dict[str, object]) -> str:
        name = PurePosixPath(urlparse(str(item["profile_url"])).path).stem
        if not name.isdigit():
            return uuid.uuid5(uuid.NAMESPACE_URL, str(item["profile_url"])).hex[:12]
        return name

    def _external_image(
        self,
        *,
        owner,
        url: str,
        business_type: str,
    ) -> ManagedFile:
        file_uuid = uuid.uuid5(uuid.NAMESPACE_URL, url)
        original_name = PurePosixPath(urlparse(url).path).name or "{0}.jpg".format(file_uuid)
        extension = PurePosixPath(original_name).suffix.lower().lstrip(".")
        mime_type = "image/png" if extension == "png" else "image/jpeg"
        file_record, _ = ManagedFile.objects.update_or_create(
            file_uuid=file_uuid,
            defaults={
                "user": owner,
                "file_path": url,
                "original_name": original_name,
                "file_ext": extension,
                "mime_type": mime_type,
                "file_size": 0,
                "file_md5": "",
                "is_public": True,
                "object_key": "",
                "storage_type": "external",
                "is_deleted": False,
                "deleted_at": None,
            },
        )
        bind_file_to_business(owner, file_record, business_type, "")
        return file_record
