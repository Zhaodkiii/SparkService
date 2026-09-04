"""公开图片上传接口（BACKOFFICE-HOSPITAL-AGENT-000002）。

按已确认演示规则不要求登录；仅接收图片，由服务端完成校验、WebP 转换、
OSS 上传与 ManagedFile 登记。不提供任何修改 ClinicalAgentProfile 的能力。
"""

from __future__ import annotations

import logging
import time
import uuid

from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from common.response import success_response
from file_manager.business_relations import bind_file_to_business
from file_manager.constants import (
    AVATAR_MAX_BYTES,
    AVATAR_OUTPUT_CONTENT_TYPE,
    UPLOAD_PURPOSE_CONFIG,
)
from file_manager.models import ManagedFile
from file_manager.serializers import PublicImageUploadSerializer
from file_manager.services.image_processing import AvatarProcessingError, build_agent_avatar
from file_manager.services.oss_object_service import OssUploadError, put_bytes
from file_manager.url_utils import managed_file_download_url
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import Hospital

logger = logging.getLogger("file_manager.public_upload")


class PublicImageUploadThrottle(AnonRateThrottle):
    scope = "public_image_upload"


class PublicImageUploadView(APIView):
    """``POST /api/v1/public/uploads/images/``：公开图片上传（仅图片）。

    安全边界：固定用途、固定 Object Key 根目录、服务端随机 UUID、
    真实图片解析、5 MB / 最长边 2048 px 限制、单 IP 限流。
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicImageUploadThrottle]

    def post(self, request):
        start_time = time.perf_counter()
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise HospitalCareError("PAYLOAD_INVALID", details={"field": "file"})
        if uploaded.size > AVATAR_MAX_BYTES:
            raise HospitalCareError("AVATAR_FILE_TOO_LARGE")

        serializer = PublicImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        hospital = Hospital.objects.filter(pk=data["hospital_id"]).first()
        if hospital is None:
            raise HospitalCareError("HOSPITAL_NOT_FOUND")
        service_user = hospital.knowledge_service_user
        if service_user is None:
            raise HospitalCareError("HOSPITAL_SERVICE_USER_REQUIRED")

        raw = uploaded.read()
        try:
            processed = build_agent_avatar(
                raw,
                crop_x=data["crop_x"],
                crop_y=data["crop_y"],
                crop_size=data["crop_size"],
            )
        except AvatarProcessingError as exc:
            raise HospitalCareError(str(exc)) from exc

        file_uuid = uuid.uuid4()
        business_type, key_template = UPLOAD_PURPOSE_CONFIG[data["purpose"]]
        object_key = key_template.format(hospital_id=hospital.id, file_uuid=file_uuid)
        try:
            put_result = put_bytes(
                object_key=object_key,
                content=processed.content,
                content_type=AVATAR_OUTPUT_CONTENT_TYPE,
            )
        except OssUploadError as exc:
            raise HospitalCareError("AVATAR_UPLOAD_FAILED") from exc

        original_name = (getattr(uploaded, "name", "") or "avatar").rsplit("/", 1)[-1][:255] or "avatar"
        file_record = ManagedFile.objects.create(
            user=service_user,
            file_uuid=file_uuid,
            file_path="",
            original_name=original_name,
            file_ext="webp",
            mime_type=AVATAR_OUTPUT_CONTENT_TYPE,
            file_size=len(processed.content),
            file_md5=processed.file_md5,
            is_public=True,
            object_key=object_key,
            storage_type="oss",
        )
        bind_file_to_business(service_user, file_record, business_type, "")

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "公开头像上传成功",
            extra={
                "file_id": file_record.id,
                "hospital_id": str(hospital.id),
                "purpose": data["purpose"],
                "object_key": object_key,
                "file_size": file_record.file_size,
                "oss_request_id": put_result.request_id,
                "duration_ms": duration_ms,
            },
        )

        base_url = managed_file_download_url(file_record)
        avatar_url = f"{base_url}?v={file_record.file_uuid}" if base_url else ""
        return success_response(
            {
                "file_id": file_record.id,
                "file_uuid": str(file_record.file_uuid),
                "mime_type": file_record.mime_type,
                "width": processed.width,
                "height": processed.height,
                "file_size": file_record.file_size,
                "avatar_url": avatar_url,
                "binding_state": "unbound",
            },
            msg="created",
            status_code=201,
        )
