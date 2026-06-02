from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.services.device_session_service import DeviceSessionService


class SparkJWTAuthentication(JWTAuthentication):
    """JWT auth with single-active-device session validation on access tokens."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, validated_token = result
        DeviceSessionService.validate_access_claims(user=user, validated_token=validated_token)
        return user, validated_token
