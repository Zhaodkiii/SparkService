import logging
import time
from django.db import DatabaseError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.http_cache import build_etag, normalize_etag
from common.response import error_response, success_response
from file_manager.models import ManagedFile
from file_manager.serializers import (
    ManagedFileBusinessUpdateSerializer,
    ManagedFileRecordSerializer,
    ManagedFileUploadSerializer,
)
from file_manager.url_utils import managed_file_download_url

logger = logging.getLogger("file_manager")
file_io_logger = logging.getLogger("file_manager.api_io")


class ManagedFileListView(APIView):
    """文件列表查询接口。支持业务维度过滤与 ETag 缓存。"""

    permission_classes = [IsAuthenticated]
    etag_max_age = 120

    def get(self, request):
        start_time = time.perf_counter()
        queryset = ManagedFile.objects.filter(user=request.user, is_deleted=False)

        business_type = request.query_params.get("business_type", "")
        business_id = request.query_params.get("business_id", "")
        is_public = request.query_params.get("is_public")
        logger.info(
            "文件列表查询请求",
            extra={
                "user_id": request.user.id,
                "business_type": business_type,
                "business_id": business_id,
                "is_public": is_public,
            },
        )

        if business_type:
            queryset = queryset.filter(business_type=business_type)
        if business_id:
            queryset = queryset.filter(business_id=business_id)
        if is_public is not None:
            queryset = queryset.filter(is_public=self._to_bool(is_public))

        etag = build_etag(
            {
                "path": request.path,
                "query": request.query_params.dict(),
                "user_id": request.user.id,
                "records": list(queryset.values_list("id", "updated_at")),
            }
        )
        incoming = normalize_etag(request.headers.get("If-None-Match"))
        if incoming and incoming == normalize_etag(etag):
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info("文件列表命中ETag缓存", extra={"user_id": request.user.id, "duration_ms": duration_ms})
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            return response

        serializer = ManagedFileRecordSerializer(queryset, many=True)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "文件列表查询成功",
            extra={"user_id": request.user.id, "record_count": len(serializer.data), "duration_ms": duration_ms},
        )
        response = success_response(serializer.data, msg="success", code=0, status_code=status.HTTP_200_OK)
        response["ETag"] = etag
        response["Cache-Control"] = f"private, max-age={self.etag_max_age}"
        return response

    def _to_bool(self, value):
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "y", "on"}


class FileRegistrationView(APIView):
    """
    文件登记接口。

    客户端直传 OSS 后调用本接口登记元数据；服务端不接收二进制文件内容。
    路径：`POST /api/v1/files/register/`
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        start_time = time.perf_counter()
        payload = self._normalize_payload(request.data)
        file_io_logger.info(
            "文件登记入参",
            extra={
                "user_id": request.user.id,
                "file_uuid": payload.get("file_uuid"),
                "original_name": payload.get("original_name"),
                "file_size": payload.get("file_size"),
                "mime_type": payload.get("mime_type"),
                "file_path": payload.get("file_path"),
                "business_type": payload.get("business_type"),
                "business_id": payload.get("business_id"),
                "is_public": payload.get("is_public"),
                "object_key": payload.get("object_key"),
                "storage_type": payload.get("storage_type"),
            },
        )
        serializer = ManagedFileUploadSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            file_record = ManagedFile.objects.create(
                user=request.user,
                file_uuid=data["file_uuid"],
                file_path=(data.get("file_path") or data["object_key"]),
                original_name=data["original_name"],
                file_ext=self._extract_ext(data["original_name"]),
                mime_type=data["mime_type"],
                file_size=data["file_size"],
                file_md5=data.get("file_md5", "").strip().lower(),
                is_public=data.get("is_public", False),
                business_type=data["business_type"],
                business_id=data.get("business_id", ""),
                object_key=data["object_key"],
                storage_type=(data.get("storage_type", "") or "oss"),
            )
        except DatabaseError:
            # 常见于数据库 schema 未完成迁移（例如缺少 object_key/storage_type 列）。
            logger.exception(
                "文件登记失败：数据库 schema 未就绪或写入异常",
                extra={"user_id": request.user.id, "file_uuid": data.get("file_uuid")},
            )
            return error_response(msg="file_register_db_error", code=5004, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "文件登记成功",
            extra={
                "user_id": request.user.id,
                "file_id": file_record.id,
                "file_uuid": str(file_record.file_uuid),
                "object_key": file_record.object_key,
                "storage_type": file_record.storage_type,
                "duration_ms": duration_ms,
            },
        )

        return success_response(
            ManagedFileRecordSerializer(file_record).data,
            msg="created",
            code=0,
            status_code=status.HTTP_201_CREATED
        )

    def _normalize_payload(self, payload):
        data = payload.copy()
        value = data.get("is_public")
        if value is not None and isinstance(value, str):
            data["is_public"] = value.lower() in {"1", "true", "yes", "y", "on"}
        return data

    def _extract_ext(self, file_name):
        if "." not in file_name:
            return ""
        return file_name.rsplit(".", 1)[-1].lower()



class ManagedFileBusinessUpdateView(APIView):
    """更新文件业务绑定信息。"""

    permission_classes = [IsAuthenticated]

    def patch(self, request):
        start_time = time.perf_counter()
        serializer = ManagedFileBusinessUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        logger.info(
            "更新文件业务绑定请求",
            extra={
                "user_id": request.user.id,
                "file_id": data["file_id"],
                "business_type": data["business_type"],
                "business_id": data.get("business_id", ""),
            },
        )

        file_record = ManagedFile.objects.filter(id=data["file_id"], user=request.user, is_deleted=False).first()
        if not file_record:
            logger.warning(
                "更新文件业务绑定失败：文件不存在",
                extra={"user_id": request.user.id, "file_id": data["file_id"]},
            )
            return error_response(msg="file_not_found", code=4040, status_code=status.HTTP_404_NOT_FOUND)

        file_record.business_type = data["business_type"]
        file_record.business_id = data.get("business_id", "")
        file_record.save(update_fields=["business_type", "business_id", "updated_at"])
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "更新文件业务绑定成功",
            extra={"user_id": request.user.id, "file_id": file_record.id, "duration_ms": duration_ms},
        )

        return success_response(ManagedFileRecordSerializer(file_record).data, msg="updated", code=0, status_code=status.HTTP_200_OK)


class ManagedFileDownloadURLView(APIView):
    """生成客户端可用的文件下载 URL（当前为直链构造）。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, file_id):
        start_time = time.perf_counter()
        logger.info("下载URL生成请求", extra={"user_id": request.user.id, "file_id": file_id})
        file_record = (
            ManagedFile.objects.filter(id=file_id, is_deleted=False)
            .filter(user=request.user)
            .first()
        )
        if not file_record:
            logger.warning("下载URL生成失败：文件不存在", extra={"user_id": request.user.id, "file_id": file_id})
            return error_response(msg="file_not_found", code=4040, status_code=status.HTTP_404_NOT_FOUND)

        url = managed_file_download_url(file_record)
        if not url:
            if not file_record.object_key:
                logger.warning("下载URL生成失败：object_key为空", extra={"user_id": request.user.id, "file_id": file_id})
                return error_response(msg="object_key_missing", code=4042, status_code=status.HTTP_404_NOT_FOUND)
            logger.error("下载URL生成失败：OSS配置缺失", extra={"file_id": file_id})
            return error_response(msg="oss_endpoint_not_configured", code=5003, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        file_io_logger.info(
            "下载URL生成成功",
            extra={
                "user_id": request.user.id,
                "file_id": file_id,
                "object_key": file_record.object_key,
                "url_prefix": normalized,
                "duration_ms": duration_ms,
            },
        )

        return success_response({"url": url}, msg="success", code=0, status_code=status.HTTP_200_OK)


class ManagedFileDeleteView(APIView):
    """文件软删除接口。"""

    permission_classes = [IsAuthenticated]

    def delete(self, request, file_id):
        start_time = time.perf_counter()
        logger.info("文件删除请求", extra={"user_id": request.user.id, "file_id": file_id})
        file_record = ManagedFile.objects.filter(id=file_id, user=request.user, is_deleted=False).first()
        if not file_record:
            logger.warning("文件删除失败：文件不存在", extra={"user_id": request.user.id, "file_id": file_id})
            return error_response(msg="file_not_found", code=4040, status_code=status.HTTP_404_NOT_FOUND)

        file_record.soft_delete()
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info("文件删除成功", extra={"user_id": request.user.id, "file_id": file_record.id, "duration_ms": duration_ms})
        return success_response({"id": file_record.id}, msg="deleted", code=0, status_code=status.HTTP_200_OK)
