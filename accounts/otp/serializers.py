from rest_framework import serializers


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
