from rest_framework import serializers


class PasswordLoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=128)
    password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=1)

    # Optional client context for audit.
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)


class TokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(min_length=1, trim_whitespace=True)


class AppleLoginSerializer(serializers.Serializer):
    identity_token = serializers.CharField(min_length=1, trim_whitespace=True)
    authorization_code = serializers.CharField(required=False, allow_blank=True)
    nonce = serializers.CharField(required=False, allow_blank=True)
    user = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=128)

    bundle_id = serializers.CharField(max_length=128)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
