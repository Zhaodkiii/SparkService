from rest_framework import serializers

from file_manager.models import ManagedFile


class ManagedFileRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManagedFile
        fields = (
            "id",
            "file_uuid",
            "original_name",
            "file_size",
            "mime_type",
            "file_md5",
            "is_public",
            "business_type",
            "business_id",
            "created_at",
        )


class ManagedFileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    business_type = serializers.CharField(max_length=64)
    business_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    is_public = serializers.BooleanField(required=False, default=False)
    file_md5 = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class ManagedFileBusinessUpdateSerializer(serializers.Serializer):
    file_id = serializers.IntegerField(min_value=1)
    business_type = serializers.CharField(max_length=64)
    business_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
