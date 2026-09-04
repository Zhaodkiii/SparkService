"""智能体头像解析、校验与立即切换（BACKOFFICE-HOSPITAL-AGENT-000002）。

规则要点：
- ``avatar_source=doctor`` 动态读取医生当前头像，不固化 URL、不复制文件。
- ``avatar_source=custom`` 必须引用合法的医院头像 ManagedFile。
- 头像文件永久保留：切换只改变引用，不删除 ManagedFile 或 OSS Object。
- 不创建头像业务审计记录；立即生效不改变 publication_status。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from django.conf import settings
from django.db import transaction

from file_manager.business_relations import bind_file_to_business
from file_manager.constants import (
    AGENT_AVATAR_KEY_TEMPLATE,
    AVATAR_OUTPUT_CONTENT_TYPE,
    BUSINESS_TYPE_CLINICAL_AGENT_AVATAR,
)
from file_manager.models import ManagedFile, ManagedFileBusinessRelation
from file_manager.url_utils import managed_file_download_url
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalAgentProfile, Hospital


@dataclass(frozen=True)
class ResolvedAvatar:
    url: str
    version: str


def _file_version_url(file_record: ManagedFile) -> str:
    base = managed_file_download_url(file_record)
    if not base:
        return ""
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}v={quote(str(file_record.file_uuid))}"


def resolve_agent_avatar(agent: ClinicalAgentProfile) -> ResolvedAvatar:
    """按头像来源解析最终展示地址与版本标识。

    解析失败（文件缺失、URL 为空）时落到统一 AI 默认头像；
    客户端再以智能体名称首字兜底。custom 来源解析失败不回退医生头像，
    避免专属头像失效时造成身份误导。
    """
    if agent.avatar_source == ClinicalAgentProfile.AvatarSource.CUSTOM:
        file_record = agent.avatar_file if agent.avatar_file_id else None
        if file_record is not None and not file_record.is_deleted:
            url = _file_version_url(file_record)
            if url:
                return ResolvedAvatar(url=url, version=f"custom:{file_record.id}:{file_record.file_uuid}")
    else:
        doctor_file = getattr(agent.doctor, "avatar_file", None)
        if doctor_file is not None and not doctor_file.is_deleted:
            url = _file_version_url(doctor_file)
            if url:
                return ResolvedAvatar(url=url, version=f"doctor:{doctor_file.id}:{doctor_file.file_uuid}")

    default_url = (getattr(settings, "CLINICAL_AGENT_DEFAULT_AVATAR_URL", "") or "").strip()
    default_version = (getattr(settings, "CLINICAL_AGENT_DEFAULT_AVATAR_VERSION", "v1") or "v1").strip()
    return ResolvedAvatar(url=default_url, version=f"default:{default_version}")


def resolve_valid_agent_avatar_file(*, hospital: Hospital, file_id) -> ManagedFile:
    """校验 file_id 是当前医院合法的智能体头像文件。"""
    if not file_id:
        raise HospitalCareError("AVATAR_SOURCE_INVALID", details={"field": "avatar_file_id"})
    file_record = (
        ManagedFile.objects.filter(pk=file_id, is_deleted=False)
        .prefetch_related("business_relations")
        .first()
    )
    if file_record is None:
        raise HospitalCareError("AVATAR_FILE_NOT_FOUND")
    if file_record.mime_type != AVATAR_OUTPUT_CONTENT_TYPE:
        raise HospitalCareError("AVATAR_FILE_FORBIDDEN", details={"reason": "mime"})
    expected_prefix = AGENT_AVATAR_KEY_TEMPLATE.split("{hospital_id}")[0] + f"{hospital.id}/"
    if not (file_record.object_key or "").startswith(expected_prefix):
        raise HospitalCareError("AVATAR_FILE_FORBIDDEN", details={"reason": "hospital"})
    if not any(
        relation.business_type == BUSINESS_TYPE_CLINICAL_AGENT_AVATAR
        for relation in file_record.business_relations.all()
    ):
        raise HospitalCareError("AVATAR_FILE_FORBIDDEN", details={"reason": "purpose"})
    return file_record


def bind_avatar_file_to_agent(*, file_record: ManagedFile, agent: ClinicalAgentProfile) -> None:
    """把头像文件归属到智能体资产集合（不是当前头像指针）。

    已存在的未绑定关系改为归属当前智能体；历史归属关系保持不变。
    """
    unbound = ManagedFileBusinessRelation.objects.filter(
        file=file_record,
        business_type=BUSINESS_TYPE_CLINICAL_AGENT_AVATAR,
        business_id="",
    ).first()
    if unbound is not None:
        ManagedFileBusinessRelation.objects.filter(pk=unbound.pk).update(business_id=str(agent.id))
        return
    bind_file_to_business(
        file_record.user,
        file_record,
        BUSINESS_TYPE_CLINICAL_AGENT_AVATAR,
        str(agent.id),
    )


@transaction.atomic
def set_agent_avatar(*, agent_id, avatar_source: str, avatar_file_id, version) -> ClinicalAgentProfile:
    """立即切换智能体头像来源；成功才返回，失败保持当前线上头像。"""
    agent = (
        ClinicalAgentProfile.objects.select_for_update()
        .select_related("hospital", "doctor", "doctor__avatar_file", "avatar_file")
        .filter(pk=agent_id)
        .first()
    )
    if agent is None:
        raise HospitalCareError("AGENT_NOT_FOUND")
    if version is None or int(version) != agent.version:
        raise HospitalCareError("AGENT_VERSION_CONFLICT", details={"version": agent.version})

    if avatar_source == ClinicalAgentProfile.AvatarSource.DOCTOR:
        agent.avatar_source = ClinicalAgentProfile.AvatarSource.DOCTOR
        agent.avatar_file = None
    elif avatar_source == ClinicalAgentProfile.AvatarSource.CUSTOM:
        file_record = resolve_valid_agent_avatar_file(hospital=agent.hospital, file_id=avatar_file_id)
        agent.avatar_source = ClinicalAgentProfile.AvatarSource.CUSTOM
        agent.avatar_file = file_record
        bind_avatar_file_to_agent(file_record=file_record, agent=agent)
    else:
        raise HospitalCareError("AVATAR_SOURCE_INVALID", details={"field": "avatar_source"})

    agent.version += 1
    agent.save(update_fields=["avatar_source", "avatar_file", "version", "updated_at"])
    return agent
