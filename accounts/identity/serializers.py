from rest_framework import serializers

from accounts.services.phone_number_service import PhoneNumberService


class IdentityListQuerySerializer(serializers.Serializer):
    bundle_id = serializers.CharField(max_length=128, required=False, allow_blank=True)


class IdentityVerificationRequestSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("phone", "email", "apple"))
    purpose = serializers.ChoiceField(choices=("bind_identity", "change_identity"))
    bundle_id = serializers.CharField(max_length=128)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class IdentityVerificationVerifySerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("phone", "email", "apple"))
    purpose = serializers.ChoiceField(choices=("bind_identity", "change_identity"))
    bundle_id = serializers.CharField(max_length=128)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    otp_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    code = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    identity_token = serializers.CharField(required=False, allow_blank=True, default="")
    authorization_code = serializers.CharField(required=False, allow_blank=True, default="")
    user_identifier = serializers.CharField(required=False, allow_blank=True, default="")


class BindIdentitySerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("phone", "email", "apple"))
    verification_ticket = serializers.CharField(max_length=256)
    bundle_id = serializers.CharField(max_length=128)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    target = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    otp_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    code = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    identity_token = serializers.CharField(required=False, allow_blank=True, default="")
    authorization_code = serializers.CharField(required=False, allow_blank=True, default="")
    user_identifier = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_target(self, value: str) -> str:
        provider = (self.initial_data.get("provider") or "").strip().lower()
        if provider == "phone" and value:
            return PhoneNumberService.normalize_e164(value)
        if provider == "email" and value:
            return value.strip().lower()
        return value


class ChangeIdentitySerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("phone", "email", "apple"))
    verification_ticket = serializers.CharField(max_length=256)
    bundle_id = serializers.CharField(max_length=128)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    new_target = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    new_otp_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    new_code = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")

    def validate_new_target(self, value: str) -> str:
        provider = (self.initial_data.get("provider") or "").strip().lower()
        if provider == "phone" and value:
            return PhoneNumberService.normalize_e164(value)
        if provider == "email" and value:
            return value.strip().lower()
        return value
