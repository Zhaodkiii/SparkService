from rest_framework import serializers


class AccountDeactivationRequestSerializer(serializers.Serializer):
    # Optional metadata for audit / future expansion.
    reason = serializers.CharField(max_length=256, required=False, allow_blank=True)
    immediate_deactivation = serializers.BooleanField(required=False, default=True)
    countdown_hours = serializers.IntegerField(required=False, min_value=1, max_value=168, default=24)
    data_retention_days = serializers.IntegerField(required=False, min_value=0, max_value=365, default=30)
    anonymize_personal_data = serializers.BooleanField(required=False, default=True)
    delete_related_data = serializers.BooleanField(required=False, default=True)
    verification = serializers.DictField(required=False)

    def validate(self, attrs):
        immediate = attrs.get("immediate_deactivation", True)
        if immediate:
            attrs["countdown_hours"] = 0
        verification = attrs.get("verification")
        if verification:
            verification_type = (verification.get("type") or "").strip().lower()
            if verification_type not in {"apple", "phone", "email"}:
                raise serializers.ValidationError({"verification": "unsupported verification type"})
            if verification_type == "apple" and not verification.get("identity_token"):
                raise serializers.ValidationError({"verification": "identity_token required"})
            if verification_type in {"phone", "email"} and (not verification.get("otp_id") or not verification.get("code")):
                raise serializers.ValidationError({"verification": "otp_id and code required"})
        return attrs


class AccountDeactivationCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=256, required=False, allow_blank=True)
