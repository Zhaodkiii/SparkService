import logging

from rest_framework import serializers

from file_manager.models import ManagedFile
from file_manager.url_utils import managed_file_download_url

logger = logging.getLogger("file_manager")


class ManagedFileRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManagedFile
        fields = (
            "id",
            "file_uuid",
            "file_path",
            "original_name",
            "file_size",
            "mime_type",
            "file_md5",
            "is_public",
            "business_type",
            "business_id",
            "object_key",
            "storage_type",
            "created_at",
        )


class ManagedFileAttachmentOutSerializer(serializers.ModelSerializer):
    """附件输出：含可直链访问的 ``file_url``（与下载接口构造规则一致）。"""

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ManagedFile
        fields = (
            "id",
            "file_uuid",
            "original_name",
            "file_size",
            "mime_type",
            "file_md5",
            "business_type",
            "business_id",
            "object_key",
            "storage_type",
            "created_at",
            "file_url",
        )

    def get_file_url(self, obj):
        return managed_file_download_url(obj)


class ManagedFileUploadSerializer(serializers.Serializer):
    file_uuid = serializers.CharField(max_length=64)
    original_name = serializers.CharField(max_length=255)
    file_size = serializers.IntegerField(min_value=0)
    mime_type = serializers.CharField(max_length=128)
    file_path = serializers.CharField(max_length=1024, required=False, allow_blank=True, default="")
    object_key = serializers.CharField(max_length=1024)
    storage_type = serializers.CharField(max_length=32, required=False, allow_blank=True, default="oss")
    business_type = serializers.CharField(max_length=64)
    business_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    is_public = serializers.BooleanField(required=False, default=False)
    file_md5 = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        cleaned = dict(attrs)
        cleaned["file_md5"] = (cleaned.get("file_md5") or "").strip().lower()
        cleaned["storage_type"] = (cleaned.get("storage_type") or "oss").strip() or "oss"
        logger.debug(
            "文件登记参数验证通过",
            extra={
                "file_uuid": cleaned.get("file_uuid"),
                "file_size": cleaned.get("file_size"),
                "mime_type": cleaned.get("mime_type"),
                "storage_type": cleaned.get("storage_type"),
            },
        )
        return cleaned

    def is_valid(self, *, raise_exception=False):
        valid = super().is_valid(raise_exception=False)
        if not valid:
            logger.warning("文件登记参数校验失败", extra={"errors": self.errors})
            if raise_exception:
                raise serializers.ValidationError(self.errors)
        return valid


class ManagedFileBusinessUpdateSerializer(serializers.Serializer):
    file_id = serializers.IntegerField(min_value=1)
    business_type = serializers.CharField(max_length=64)
    business_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")

    def is_valid(self, *, raise_exception=False):
        valid = super().is_valid(raise_exception=False)
        if not valid:
            logger.warning("文件绑定更新参数校验失败", extra={"errors": self.errors})
            if raise_exception:
                raise serializers.ValidationError(self.errors)
        return valid
