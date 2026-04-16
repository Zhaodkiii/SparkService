from rest_framework import serializers

from accounts.services.phone_number_service import PhoneNumberService


class EmailOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    provider_uid = serializers.CharField(max_length=128, required=False, allow_blank=True)
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)


class EmailOTPVerifySerializer(serializers.Serializer):
    otp_id = serializers.CharField(max_length=64)
    email = serializers.EmailField()
    code = serializers.CharField(max_length=16, min_length=4)
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)


class PhoneOTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=32)
    provider_uid = serializers.CharField(max_length=128, required=False, allow_blank=True)
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)

    def validate_phone_number(self, value: str) -> str:
        return PhoneNumberService.normalize_e164(value)


class PhoneOTPVerifySerializer(serializers.Serializer):
    otp_id = serializers.CharField(max_length=64)
    phone_number = serializers.CharField(max_length=32)
    code = serializers.CharField(max_length=16, min_length=4)
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)

    def validate_phone_number(self, value: str) -> str:
        return PhoneNumberService.normalize_e164(value)
