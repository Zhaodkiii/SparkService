from rest_framework import serializers

from app_version.models import AppVersionConfig, UpdateActionLog, VersionCheckLog
from app_version.utils import compare_builds, compare_versions


class VersionCheckRequestSerializer(serializers.Serializer):
    version = serializers.CharField(max_length=50)
    build = serializers.CharField(required=False, allow_blank=True, max_length=50, default="")
    platform = serializers.ChoiceField(choices=AppVersionConfig.Platform.choices)
    device_id = serializers.CharField(max_length=255)
    bundle_id = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    channel = serializers.ChoiceField(required=False, choices=AppVersionConfig.Channel.choices, default=AppVersionConfig.Channel.PRODUCTION)
    system_version = serializers.CharField(required=False, allow_blank=True, max_length=50, default="")

    def validate_version(self, value):
        try:
            compare_versions(value, value)
        except ValueError:
            raise serializers.ValidationError("version_must_be_dot_separated_integers")
        return value

    def validate_build(self, value):
        if value:
            compare_builds(value, value)
        return value


class VersionCheckResponseSerializer(serializers.Serializer):
    checkLogId = serializers.IntegerField(required=False, allow_null=True)
    hasUpdate = serializers.BooleanField()
    latestVersion = serializers.CharField(required=False, allow_blank=True)
    latestBuild = serializers.CharField(required=False, allow_blank=True)
    forceUpdate = serializers.BooleanField(required=False)
    updateTitle = serializers.CharField(required=False, allow_blank=True)
    updateMessage = serializers.CharField(required=False, allow_blank=True)
    downloadUrl = serializers.CharField(required=False, allow_blank=True)
    releaseNotes = serializers.CharField(required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)


class UpdateActionRequestSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=UpdateActionLog.Action.choices)
    check_log_id = serializers.IntegerField(required=False, allow_null=True)
    device_id = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    platform = serializers.CharField(required=False, allow_blank=True, max_length=20, default="")
    bundle_id = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")


class AppVersionConfigSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = AppVersionConfig
        fields = (
            "id",
            "platform",
            "bundle_id",
            "channel",
            "latest_version",
            "latest_build",
            "force_update_min_version",
            "force_update_min_build",
            "update_title",
            "update_message",
            "release_notes",
            "download_url",
            "enable_gradual_release",
            "gradual_release_percentage",
            "gradual_release_min_version",
            "is_active",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_by", "created_by_name", "created_at", "updated_at")

    def validate(self, attrs):
        for key in ("latest_version", "force_update_min_version", "gradual_release_min_version"):
            value = attrs.get(key)
            if value:
                try:
                    compare_versions(value, value)
                except ValueError:
                    raise serializers.ValidationError({key: "version_must_be_dot_separated_integers"})
        percentage = attrs.get("gradual_release_percentage")
        if percentage is not None and (percentage < 0 or percentage > 100):
            raise serializers.ValidationError({"gradual_release_percentage": "percentage_must_be_0_100"})
        return attrs


class VersionCheckLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = VersionCheckLog
        fields = (
            "id",
            "platform",
            "bundle_id",
            "channel",
            "current_version",
            "current_build",
            "device_id",
            "system_version",
            "user",
            "user_name",
            "config",
            "has_update",
            "force_update",
            "latest_version",
            "latest_build",
            "decision_reason",
            "ip_address",
            "request_id",
            "checked_at",
        )

