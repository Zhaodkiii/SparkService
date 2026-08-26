from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

from accounts.services.device_session_service import DeviceSessionService
from accounts.services.web_session_service import WebSessionService


class SparkJWTAuthentication(JWTAuthentication):
    """JWT auth with session-class dispatch (CHAT-WEB-019).

    - web_session_id + session_class=web -> AccountWebSession validation
    - device_session_id -> existing single-active-device validation
    - both claims -> reject as a forged token
    - no session claim -> plain SimpleJWT (admin/legacy password tokens)
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, validated_token = result
        claims = DeviceSessionService._claims_from_validated_token(validated_token)
        if WebSessionService.claims_conflict_session_classes(claims):
            raise AuthenticationFailed(WebSessionService.WEB_SESSION_CLASS_CONFLICT)
        if WebSessionService.claims_require_web_session(claims):
            WebSessionService.validate_access_claims(user=user, validated_token=validated_token)
            return user, validated_token
        DeviceSessionService.validate_access_claims(user=user, validated_token=validated_token)
        return user, validated_token
