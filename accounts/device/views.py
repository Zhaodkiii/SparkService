import logging

from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from accounts.auth.authentication import SparkJWTAuthentication
from accounts.services.device_session_service import DeviceSessionService
from common.exceptions import APIError
from common.response import success_response
from accounts.device.serializers import DeviceRegisterSerializer
from accounts.services.device_service import DeviceService

flow_logger = logging.getLogger("accounts.flow")


class DeviceRegisterAnonThrottle(AnonRateThrottle):
    """Throttle anonymous device registration bursts."""

    rate = "120/hour"


def _authorization_header_present(request) -> bool:
    auth = request.headers.get("Authorization") or request.META.get("HTTP_AUTHORIZATION")
    return bool(auth and str(auth).strip())


def _authentication_failure_message(exc: AuthenticationFailed) -> str:
    detail = exc.detail
    if isinstance(detail, str):
        return detail.strip() or "authentication_failed"
    if isinstance(detail, list) and detail:
        first = detail[0]
        return str(first).strip() if first else "authentication_failed"
    if isinstance(detail, dict):
        for value in detail.values():
            if isinstance(value, list) and value:
                return str(value[0]).strip()
            if value:
                return str(value).strip()
    return "authentication_failed"


# 设备注册接口视图
class DeviceRegisterView(APIView):
    """
    设备注册接口
    POST 请求地址：/api/v1/device/register/

    权限说明：
    1. 无 Authorization：匿名登记或更新 revoked 用户行（见 ACCOUNTS-000003）；可带 `user_id` 辅助定位上次登录用户。
    2. 有 Authorization：必须 JWT + 有效设备会话；失效返回 401，不降级匿名登记。
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [DeviceRegisterAnonThrottle]

    def post(self, request):
        has_auth_header = _authorization_header_present(request)
        user = None

        if has_auth_header:
            auth = SparkJWTAuthentication()
            try:
                result = auth.authenticate(request)
            except (InvalidToken, TokenError) as exc:
                flow_logger.warning(
                    "device.register.rejected_invalid_token",
                    extra={"action": "device.register", "reason": str(exc)},
                )
                raise APIError("token_not_valid", code=40102, status_code=401) from exc
            except AuthenticationFailed as exc:
                msg = _authentication_failure_message(exc)
                flow_logger.warning(
                    "device.register.rejected_auth_failed",
                    extra={"action": "device.register", "reason": msg},
                )
                raise APIError(msg, code=40102, status_code=401) from exc

            if result is None:
                flow_logger.warning(
                    "device.register.rejected_missing_user",
                    extra={"action": "device.register"},
                )
                raise APIError("token_not_valid", code=40102, status_code=401)
            user, _token = result

        serializer = DeviceRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        request_id = getattr(request, "request_id", "") or ""
        explicit_keys = set(request.data.keys())

        if user is not None:
            data = serializer.validated_data
            bundle_id = (data.get("bundle_id") or data.get("bundle_identifier") or "").strip()
            device_id = (data.get("device_id") or "").strip()
            try:
                DeviceSessionService.validate_authenticated_device_register(
                    user=user,
                    bundle_id=bundle_id,
                    device_id=device_id,
                )
            except APIError:
                flow_logger.warning(
                    "device.register.rejected_inactive_session",
                    extra={
                        "action": "device.register",
                        "request_id": request_id,
                        "user_id": user.id,
                        "bundle_id": bundle_id,
                        "device_id": device_id,
                    },
                )
                raise

        out = DeviceService.register_device(
            user=user,
            data=serializer.validated_data,
            explicit_keys=explicit_keys,
            request_id=request_id,
        )

        return success_response(
            data=out,
            msg="device_registered",
            code=0,
            status_code=status.HTTP_200_OK,
        )
