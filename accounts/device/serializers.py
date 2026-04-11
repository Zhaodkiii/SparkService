from rest_framework import serializers


class DeviceRegisterSerializer(serializers.Serializer):
    """Full device registration payload (aligned with HealthClient DeviceRegistrationRequest)."""

    device_id = serializers.CharField(max_length=255)
    user_id = serializers.IntegerField(required=False, allow_null=True)
    push_token = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")
    notifications_enabled = serializers.BooleanField(required=False, default=False)
    app_version = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    build_version = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    bundle_identifier = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    bundle_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    platform = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    system_version = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    device_model = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    device_model_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    device_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    screen_size = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    screen_scale = serializers.FloatField(required=False, allow_null=True)
    time_zone = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    language_code = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    region_code = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    is_simulator = serializers.BooleanField(required=False, default=False)
