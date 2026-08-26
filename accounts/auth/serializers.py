from rest_framework import serializers

from accounts.services.phone_number_service import PhoneNumberService


class PasswordLoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=128)
    password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=1)

    # Optional client context for audit.
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)


class TokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(min_length=1, trim_whitespace=True, required=False)
    refresh_token = serializers.CharField(min_length=1, trim_whitespace=True, required=False)
    bundle_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        refresh_token = attrs.get("refresh_token") or attrs.get("refresh")
        if not refresh_token:
            raise serializers.ValidationError({"refresh_token": "This field is required."})
        attrs["refresh_token"] = refresh_token
        return attrs


class AppleLoginSerializer(serializers.Serializer):
    identity_token = serializers.CharField(min_length=1, trim_whitespace=True)
    authorization_code = serializers.CharField(required=False, allow_blank=True)
    nonce = serializers.CharField(required=False, allow_blank=True)
    user = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=128)

    bundle_id = serializers.CharField(max_length=128)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_secret = serializers.CharField(max_length=512, required=False, allow_blank=True, trim_whitespace=True)


class DeviceLoginSerializer(serializers.Serializer):
    bundle_id = serializers.CharField(max_length=128)
    device_id = serializers.CharField(max_length=255)
    device_secret = serializers.CharField(max_length=512, trim_whitespace=True)
    attestation = serializers.CharField(required=False, allow_blank=True, max_length=8192)


class WebAppleLoginSerializer(serializers.Serializer):
    """Chat Web Apple 登录契约（CHAT-WEB-019）：拒绝一切移动端字段。"""

    identity_token = serializers.CharField(min_length=1, trim_whitespace=True)
    authorization_code = serializers.CharField(required=False, allow_blank=True)
    nonce = serializers.CharField(min_length=1, trim_whitespace=True)
    service_id = serializers.CharField(max_length=128)
    redirect_uri = serializers.CharField(max_length=512, required=False, allow_blank=True)
    user = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=128)

    def validate(self, attrs):
        # 移动端字段在 Web 入口一律非法：防止 BFF 或攻击者借 Web 入口进入设备会话域。
        forbidden = ("bundle_id", "device_id", "device_secret")
        rejected = [field for field in forbidden if field in self.initial_data]
        if rejected:
            raise serializers.ValidationError(
                {field: "This field is not accepted by the web Apple login endpoint." for field in rejected}
            )
        return attrs


class WebPhoneOTPRequestSerializer(serializers.Serializer):
    """Chat Web 手机 OTP 请求契约（CHAT-WEB-020）：拒绝一切移动端字段，只接受 scene=login。"""

    phone_number = serializers.CharField(max_length=32)
    scene = serializers.ChoiceField(choices=("login",), required=False, default="login")

    def validate_phone_number(self, value: str) -> str:
        return PhoneNumberService.normalize_e164(value)

    def validate(self, attrs):
        forbidden = ("bundle_id", "device_id", "device_secret", "user_id", "provider_uid")
        rejected = [field for field in forbidden if field in self.initial_data]
        if rejected:
            raise serializers.ValidationError(
                {field: "This field is not accepted by the web phone OTP endpoint." for field in rejected}
            )
        return attrs


class WebPhoneOTPVerifySerializer(serializers.Serializer):
    otp_id = serializers.CharField(max_length=64)
    phone_number = serializers.CharField(max_length=32)
    code = serializers.CharField(max_length=16, min_length=4)

    def validate_phone_number(self, value: str) -> str:
        return PhoneNumberService.normalize_e164(value)

    def validate(self, attrs):
        forbidden = ("bundle_id", "device_id", "device_secret", "user_id")
        rejected = [field for field in forbidden if field in self.initial_data]
        if rejected:
            raise serializers.ValidationError(
                {field: "This field is not accepted by the web phone OTP endpoint." for field in rejected}
            )
        return attrs
