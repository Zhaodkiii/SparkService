from rest_framework import serializers


class AccountDeactivationRequestSerializer(serializers.Serializer):
    # Optional metadata for audit / future expansion.
    reason = serializers.CharField(max_length=256, required=False, allow_blank=True)
    immediate_deactivation = serializers.BooleanField(required=False, default=True)
    countdown_hours = serializers.IntegerField(required=False, min_value=1, max_value=168, default=24)

    def validate(self, attrs):
        immediate = attrs.get("immediate_deactivation", True)
        if immediate:
            attrs["countdown_hours"] = 0
        return attrs


class AccountDeactivationCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=256, required=False, allow_blank=True)
