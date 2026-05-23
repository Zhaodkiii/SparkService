import logging

from rest_framework import serializers

from file_manager.business_relations import files_for_business
from file_manager.models import ManagedFile
from file_manager.url_utils import managed_file_download_url

logger = logging.getLogger("file_manager")


class ManagedFileRecordSerializer(serializers.ModelSerializer):
    business_type = serializers.SerializerMethodField()
    business_id = serializers.SerializerMethodField()

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

    def _first_relation(self, obj):
        preferred = self._preferred_relation(obj)
        if preferred is not None:
            return preferred
        if hasattr(obj, "_prefetched_objects_cache") and "business_relations" in obj._prefetched_objects_cache:
            relations = obj._prefetched_objects_cache["business_relations"]
            return relations[0] if relations else None
        return obj.business_relations.order_by("-created_at", "-id").first()

    def _preferred_relation(self, obj):
        bt = self.context.get("business_type")
        bid = self.context.get("business_id")
        if not bt and not bid:
            return None
        queryset = obj.business_relations.all()
        if bt:
            queryset = queryset.filter(business_type=bt)
        if bid:
            queryset = queryset.filter(business_id=str(bid))
        return queryset.order_by("-created_at", "-id").first()

    def get_business_type(self, obj):
        relation = self._first_relation(obj)
        return relation.business_type if relation else ""

    def get_business_id(self, obj):
        relation = self._first_relation(obj)
        return relation.business_id if relation else ""


class ManagedFileAttachmentOutSerializer(serializers.ModelSerializer):
    """附件输出：含可直链访问的 ``file_url``（与下载接口构造规则一致）。"""

    file_url = serializers.SerializerMethodField()
    business_type = serializers.SerializerMethodField()
    business_id = serializers.SerializerMethodField()

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

    def _first_relation(self, obj):
        preferred = self._preferred_relation(obj)
        if preferred is not None:
            return preferred
        if hasattr(obj, "_prefetched_objects_cache") and "business_relations" in obj._prefetched_objects_cache:
            relations = obj._prefetched_objects_cache["business_relations"]
            return relations[0] if relations else None
        return obj.business_relations.order_by("-created_at", "-id").first()

    def _preferred_relation(self, obj):
        bt = self.context.get("business_type")
        bid = self.context.get("business_id")
        if not bt and not bid:
            return None
        queryset = obj.business_relations.all()
        if bt:
            queryset = queryset.filter(business_type=bt)
        if bid:
            queryset = queryset.filter(business_id=str(bid))
        return queryset.order_by("-created_at", "-id").first()

    def get_business_type(self, obj):
        relation = self._first_relation(obj)
        return relation.business_type if relation else ""

    def get_business_id(self, obj):
        relation = self._first_relation(obj)
        return relation.business_id if relation else ""


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


class HasAttachmentsMixin(serializers.Serializer):
    """
    给任意 ModelSerializer 快速加上 ``attachments`` 字段。

    用法
    ----
    1. 子类设置 ``attachments_business_type``（推荐），或在 ``context`` 里传
       ``"attachments_business_type"``；
    2. 在 ``Meta.fields`` 里包含 ``"attachments"``；
    3. 调用时确保 ``context["request"]`` 存在；附件按成员绑定可访问的业务资源返回（非仅上传者本人）。

    可选项
    ------
    - ``context["with_attachments"]=False`` 或构造时 ``with_attachments=False``
      可以关闭附件查询（列表场景节省 N+1）。
    - 子类可重载 ``_attachments_business_id`` 从对象里提取业务 ID（默认 ``obj.id``）。
    - 未登录、缺失 business_type/business_id 时一律返回 ``[]``。
    """

    attachments = serializers.SerializerMethodField()

    attachments_business_type: str = None

    def __init__(self, *args, **kwargs):
        self.with_attachments = kwargs.pop("with_attachments", None)
        super().__init__(*args, **kwargs)

    def _attachments_business_id(self, obj):
        return getattr(obj, "id", None)

    def get_attachments(self, obj):
        enabled = self.with_attachments
        if enabled is None:
            enabled = self.context.get("with_attachments", True)
        if not enabled:
            return []

        bt = self.attachments_business_type or self.context.get("attachments_business_type")
        if not bt:
            return []

        bid = self._attachments_business_id(obj)
        if not bid:
            return []

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return []

        qs = files_for_business(user, bt, bid)
        return ManagedFileAttachmentOutSerializer(
            qs,
            many=True,
            context={"business_type": bt, "business_id": str(bid)},
        ).data
