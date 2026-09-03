from __future__ import annotations

import logging

from hospital_care.models import ClinicalConversationBinding, DoctorProfile, HospitalStaffMembership
from hospital_care.realtime.notifier import DoctorConversationNotifier

logger = logging.getLogger("hospital_care.realtime")


def dispatch_doctor_conversation_hint(*, thread_id, message_id: str, cursor: str) -> None:
    """BACKOFFICE-CONVERSATION-000002：事务提交后向会话绑定医生分发无正文变化提示。

    - thread_id 一对一对应会话绑定，不按患者、医院或科室扩大范围。
    - 会话已终结、绑定不存在、医生档案/成员关系失效时不再下发。
    - 查询或分发失败只记录诊断，不影响消息主流程。
    """
    try:
        binding = (
            ClinicalConversationBinding.objects.select_related("doctor", "doctor__staff_membership")
            .filter(thread_id=thread_id)
            .first()
        )
    except Exception:
        logger.exception("doctor conversation dispatch query failed thread_id=%s", thread_id)
        return
    if binding is None:
        return
    if binding.service_status == ClinicalConversationBinding.ServiceStatus.ENDED:
        return
    doctor = binding.doctor
    membership = getattr(doctor, "staff_membership", None)
    if doctor.profile_status != DoctorProfile.ProfileStatus.ACTIVE:
        return
    if membership is None or membership.status != HospitalStaffMembership.Status.ACTIVE:
        return
    DoctorConversationNotifier.notify_conversation_updated(
        doctor_id=doctor.id,
        thread_id=thread_id,
        message_ids=[message_id],
        cursor=cursor,
    )
