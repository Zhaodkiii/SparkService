import logging

from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from common.response import success_response
from accounts.device.serializers import DeviceRegisterSerializer
from accounts.services.device_service import DeviceService

flow_logger = logging.getLogger("accounts.flow")


class DeviceRegisterAnonThrottle(AnonRateThrottle):
    """Throttle anonymous device registration bursts."""

    rate = "120/hour"


class DeviceRegisterView(APIView):
    """
    POST /api/v1/device/register/
    AllowAny: optional Bearer JWT; when valid, rows are bound to that user.
    JWT is parsed only in post() so invalid tokens do not return 401.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [DeviceRegisterAnonThrottle]

    def post(self, request):
        user = None
        try:
            auth = JWTAuthentication()
            result = auth.authenticate(request)
            if result is not None:
                user, _token = result
        except (InvalidToken, TokenError, AuthenticationFailed) as exc:
            flow_logger.debug(
                "device.register.optional_jwt_skip",
                extra={"action": "device.register", "reason": str(exc)},
            )

        serializer = DeviceRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        request_id = getattr(request, "request_id", "") or ""
        explicit_keys = set(request.data.keys())
        out = DeviceService.register_device(
            user=user,
            data=serializer.validated_data,
            explicit_keys=explicit_keys,
            request_id=request_id,
        )
        return success_response(out, msg="device_registered", code=0, status_code=status.HTTP_200_OK)
