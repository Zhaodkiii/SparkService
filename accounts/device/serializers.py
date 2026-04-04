from rest_framework import serializers


class DeviceRegisterSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=128)
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    nickname = serializers.CharField(max_length=64, required=False, allow_blank=True)

