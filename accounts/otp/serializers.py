from rest_framework import serializers

from accounts.services.phone_number_service import PhoneNumberService


class EmailOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    provider_uid = serializers.CharField(max_length=128, required=False, allow_blank=True)
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    scene = serializers.ChoiceField(
        choices=("login", "registration", "identity_bind", "identity_change", "identity_reauth", "password_reset"),
        required=False,
        allow_blank=True,
        default="login",
    )


class EmailOTPVerifySerializer(serializers.Serializer):
    otp_id = serializers.CharField(max_length=64)
    email = serializers.EmailField()
    code = serializers.CharField(max_length=16, min_length=4)
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_secret = serializers.CharField(max_length=512, required=False, allow_blank=True, trim_whitespace=True)


class PhoneOTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=32)
    provider_uid = serializers.CharField(max_length=128, required=False, allow_blank=True)
    bundle_id = serializers.CharField(max_length=128)
    device_id = serializers.CharField(max_length=128)
    scene = serializers.ChoiceField(
        choices=("login", "account_deactivation", "identity_bind", "identity_change", "identity_reauth"),
        required=False,
        allow_blank=True,
        default="login",
    )
    user_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate_phone_number(self, value: str) -> str:
        return PhoneNumberService.normalize_e164(value)


class PhoneOTPVerifySerializer(serializers.Serializer):
    otp_id = serializers.CharField(max_length=64)
    phone_number = serializers.CharField(max_length=32)
    code = serializers.CharField(max_length=16, min_length=4)
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_secret = serializers.CharField(max_length=512, required=False, allow_blank=True, trim_whitespace=True)

    def validate_phone_number(self, value: str) -> str:
        return PhoneNumberService.normalize_e164(value)
