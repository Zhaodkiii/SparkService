import logging

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenRefreshSerializer as SimpleJWTTokenRefreshSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

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

        provided_refresh = serializer.validated_data["refresh_token"]
        simplejwt_serializer = SimpleJWTTokenRefreshSerializer(data={"refresh": provided_refresh})
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
        resolved_refresh = data.get("refresh") or provided_refresh
        try:
            user_id = int(RefreshToken(resolved_refresh)["user_id"])
        except Exception:
            flow_logger.warning(
                "刷新访问令牌失败：refresh 中 user_id 无效",
                extra={"action": "auth.token.refresh", "outcome": "failed", "request_id": request_id, "reason": "invalid_user_id"},
            )
            raise APIError("token_not_valid", code=40102, status_code=status.HTTP_401_UNAUTHORIZED)
        return Response(
            {
                "user_id": user_id,
                "access_token": data["access"],
                # Keep refresh when rotate is enabled; otherwise return null and client keeps old one.
                "refresh_token": data.get("refresh"),
                "token_type": "Bearer",
            },
            status=status.HTTP_200_OK,
        )


class TokenObtainUnifiedView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = TokenObtainPairSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            raise APIError("Invalid credentials", code=40101, status_code=status.HTTP_401_UNAUTHORIZED)

        data = serializer.validated_data
        refresh_token = data["refresh"]
        try:
            refresh = RefreshToken(refresh_token)
            user_id = int(refresh["user_id"])
        except Exception:
            raise APIError("token_not_valid", code=40102, status_code=status.HTTP_401_UNAUTHORIZED)

        user = get_user_model().objects.filter(id=user_id).only("id", "is_active").first()
        if not user or not user.is_active:
            raise APIError("user_inactive", code=40103, status_code=status.HTTP_401_UNAUTHORIZED)

        return Response(
            {
                "user_id": user_id,
                "access_token": data["access"],
                "refresh_token": refresh_token,
                "token_type": "Bearer",
            },
            status=status.HTTP_200_OK,
        )


from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework import status


# 苹果第三方登录接口视图
class AppleLoginView(APIView):
    # 权限设置：允许所有用户访问（未登录/游客均可请求）
    permission_classes = [AllowAny]

    def post(self, request):
        """
        处理苹果登录的POST请求
        接收前端传递的苹果授权参数，完成认证、用户注册/登录、颁发令牌
        :param request: 请求对象，包含苹果登录相关参数
        :return: 统一格式的登录成功响应（含用户信息、token等）
        """
        # 获取请求唯一标识（用于日志追踪、问题排查）
        request_id = getattr(request, "request_id", "") or ""

        # 记录日志：苹果登录接口请求开始
        flow_logger.info(
            "Apple 登录接口请求开始",
            extra={"action": "auth.apple.login", "path": request.path, "method": request.method,
                   "request_id": request_id},
        )

        # 初始化序列化器，校验前端传入的苹果登录参数合法性
        serializer = AppleLoginSerializer(data=request.data)
        # 参数校验失败时，直接抛出异常并返回错误响应
        serializer.is_valid(raise_exception=True)

        # 获取请求头元信息
        meta = request.META
        # 获取客户端真实IP地址（优先获取代理IP，无则获取直接连接IP）
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        # 获取客户端浏览器/设备信息
        user_agent = meta.get("HTTP_USER_AGENT", "") or ""
        # 获取序列化器校验通过后的合法数据
        data = serializer.validated_data

        # 调用登录服务层：执行苹果登录核心逻辑（认证、创建/更新用户、颁发token）
        result = LoginService.authenticate_apple_and_issue_tokens(
            identity_token=data["identity_token"],  # 苹果授权的身份令牌
            bundle_id=data["bundle_id"],  # 应用Bundle ID（iOS应用标识）
            nonce=data.get("nonce", "") or "",  # 随机字符串，防重放攻击
            user_identifier=data.get("user", "") or "",  # 苹果用户唯一标识
            email=data.get("email", "") or "",  # 用户邮箱（苹果可能加密）
            full_name=data.get("full_name", "") or "",  # 用户姓名
            ip_address=ip_address,  # 客户端IP
            user_agent=user_agent,  # 客户端设备信息
            device_id=data.get("device_id", "") or "",  # 设备唯一标识
            request_id=getattr(request, "request_id", "") or "",  # 请求追踪ID
        )

        # 记录日志：苹果登录成功，记录关键信息（用户ID、是否新用户等）
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

        # 返回统一格式的成功响应
        return success_response(result, msg="login_success", code=0, status_code=status.HTTP_200_OK)