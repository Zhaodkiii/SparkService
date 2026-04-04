import logging

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework_simplejwt.serializers import TokenRefreshSerializer as SimpleJWTTokenRefreshSerializer

from accounts.auth.serializers import AppleLoginSerializer, PasswordLoginSerializer, TokenRefreshSerializer
from accounts.services.login_service import LoginService
from common.exceptions import APIError
from common.response import success_response

flow_logger = logging.getLogger("accounts.flow")


class PasswordLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "密码登录开始",
            extra={"action": "auth.password.login", "path": request.path, "method": request.method, "request_id": request_id},
        )
        serializer = PasswordLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        user_agent = meta.get("HTTP_USER_AGENT", "") or ""

        data = serializer.validated_data
        result = LoginService.authenticate_and_issue_tokens(
            identifier=data["identifier"],
            password=data["password"],
            ip_address=ip_address,
            user_agent=user_agent,
            bundle_id=data.get("bundle_id", "") or "",
            device_id=data.get("device_id", "") or "",
            request_id=getattr(request, "request_id", "") or "",
            provider="password",
        )
        flow_logger.info(
            "密码登录成功",
            extra={
                "action": "auth.password.login",
                "outcome": "success",
                "request_id": request_id,
                "user_id": result.get("user_id"),
                "provider": "password",
            },
        )
        return success_response(result, msg="login_success", code=0, status_code=status.HTTP_200_OK)


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "刷新访问令牌开始",
            extra={"action": "auth.token.refresh", "path": request.path, "method": request.method, "request_id": request_id},
        )
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        simplejwt_serializer = SimpleJWTTokenRefreshSerializer(data={"refresh": serializer.validated_data["refresh"]})
        try:
            simplejwt_serializer.is_valid(raise_exception=True)
        except Exception:
            # SparkClient expects direct JSON on success. On failure we keep backend error schema.
            flow_logger.warning(
                "刷新访问令牌失败",
                extra={"action": "auth.token.refresh", "outcome": "failed", "request_id": request_id, "reason": "token_not_valid"},
            )
            raise APIError("token_not_valid", code=40102, status_code=status.HTTP_401_UNAUTHORIZED)

        data = simplejwt_serializer.validated_data
        return Response(
            {
                "access": data["access"],
                # Keep refresh when rotate is enabled; otherwise return null and client keeps old one.
                "refresh": data.get("refresh"),
            },
            status=status.HTTP_200_OK,
        )


class AppleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "Apple 登录接口请求开始",
            extra={"action": "auth.apple.login", "path": request.path, "method": request.method, "request_id": request_id},
        )
        serializer = AppleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        user_agent = meta.get("HTTP_USER_AGENT", "") or ""
        data = serializer.validated_data

        result = LoginService.authenticate_apple_and_issue_tokens(
            identity_token=data["identity_token"],
            bundle_id=data["bundle_id"],
            nonce=data.get("nonce", "") or "",
            user_identifier=data.get("user", "") or "",
            email=data.get("email", "") or "",
            full_name=data.get("full_name", "") or "",
            ip_address=ip_address,
            user_agent=user_agent,
            device_id=data.get("device_id", "") or "",
            request_id=getattr(request, "request_id", "") or "",
        )
        flow_logger.info(
            "Apple 登录成功",
            extra={
                "action": "auth.apple.login",
                "outcome": "success",
                "request_id": request_id,
                "user_id": result.get("user_id"),
                "provider": "apple",
                "is_new_user": result.get("is_new_user", False),
            },
        )
        return success_response(result, msg="login_success", code=0, status_code=status.HTTP_200_OK)
