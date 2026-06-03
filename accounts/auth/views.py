import logging

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenRefreshSerializer as SimpleJWTTokenRefreshSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.auth.authentication import SparkJWTAuthentication
from accounts.auth.serializers import AppleLoginSerializer, PasswordLoginSerializer, TokenRefreshSerializer
from accounts.services.device_session_service import DeviceSessionService
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
        bundle_id = serializer.validated_data.get("bundle_id", "") or ""
        device_id = serializer.validated_data.get("device_id", "") or ""

        try:
            refresh_claims = dict(RefreshToken(provided_refresh).payload)
        except Exception:
            flow_logger.warning(
                "刷新访问令牌失败",
                extra={"action": "auth.token.refresh", "outcome": "failed", "request_id": request_id, "reason": "token_not_valid"},
            )
            raise APIError("token_not_valid", code=40102, status_code=status.HTTP_401_UNAUTHORIZED)

        if not DeviceSessionService.claims_require_device_session(refresh_claims):
            simplejwt_serializer = SimpleJWTTokenRefreshSerializer(data={"refresh": provided_refresh})
            try:
                simplejwt_serializer.is_valid(raise_exception=True)
            except Exception:
                flow_logger.warning(
                    "刷新访问令牌失败",
                    extra={"action": "auth.token.refresh", "outcome": "failed", "request_id": request_id, "reason": "token_not_valid"},
                )
                raise APIError("token_not_valid", code=40102, status_code=status.HTTP_401_UNAUTHORIZED) from None
            data = simplejwt_serializer.validated_data
            try:
                user_id = int(RefreshToken(data.get("refresh") or provided_refresh)["user_id"])
            except Exception:
                raise APIError("token_not_valid", code=40102, status_code=status.HTTP_401_UNAUTHORIZED) from None
            return Response(
                {
                    "user_id": user_id,
                    "access_token": data["access"],
                    "refresh_token": data.get("refresh"),
                    "token_type": "Bearer",
                },
                status=status.HTTP_200_OK,
            )

        try:
            user, session, _claims = DeviceSessionService.validate_refresh_request(
                refresh_token_str=provided_refresh,
                bundle_id=bundle_id,
                device_id=device_id,
            )
        except APIError:
            flow_logger.warning(
                "刷新访问令牌失败：设备会话校验未通过",
                extra={"action": "auth.token.refresh", "outcome": "failed", "request_id": request_id},
            )
            raise

        tokens = DeviceSessionService.rotate_tokens_after_refresh(
            user=user,
            session=session,
            old_refresh_str=provided_refresh,
            bundle_id=bundle_id or session.bundle_id,
            device_id=device_id or session.device_id,
        )
        flow_logger.info(
            "刷新访问令牌成功",
            extra={
                "action": "auth.token.refresh",
                "outcome": "success",
                "request_id": request_id,
                "user_id": user.id,
                "session_id": session.id,
            },
        )
        return Response(
            {
                "user_id": tokens["user_id"],
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "token_type": tokens["token_type"],
            },
            status=status.HTTP_200_OK,
        )



class TokenObtainUnifiedView(APIView):
    """
    统一登录签发Token接口
    逻辑：账号密码校验 -> simplejwt生成双Token -> 从refresh载荷解析用户ID -> 校验用户状态 -> 返回标准化token结构
    开放匿名访问，无需携带登录鉴权头
    """
    # 放行所有请求，无需登录鉴权
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        """
        POST 登录获取 access/refresh 令牌
        :param request: 请求体携带username/password
        :return: user_id + access_token + refresh_token 标准化返回
        错误码：
            40101：账号密码错误、序列化校验失败
            40102：refresh令牌解析异常、过期、篡改无效
            40103：用户不存在或账号已禁用
        """
        # 实例化simplejwt账号密码序列化器
        serializer = TokenObtainPairSerializer(data=request.data)
        try:
            # 校验账号密码，失败直接抛异常
            serializer.is_valid(raise_exception=True)
        except Exception:
            # 账号/密码错误，自定义错误返回
            raise APIError("Invalid credentials", code=40101, status_code=status.HTTP_401_UNAUTHORIZED)

        # 校验通过，取出序列化生成的access、refresh原始token
        data = serializer.validated_data
        refresh_token = data["refresh"]
        try:
            # 用refresh_token反解析JWT载荷，提取user_id
            refresh = RefreshToken(refresh_token)
            user_id = int(refresh["user_id"])
        except Exception:
            # refresh令牌非法、过期、被篡改
            raise APIError("token_not_valid", code=40102, status_code=status.HTTP_401_UNAUTHORIZED)

        # 根据user_id查询用户，仅查id、is_active字段优化性能
        user = get_user_model().objects.filter(id=user_id).only("id", "is_active").first()
        # 用户不存在 / 用户被禁用
        if not user or not user.is_active:
            raise APIError("user_inactive", code=40103, status_code=status.HTTP_401_UNAUTHORIZED)

        # 组装统一格式Token返回体
        return Response(
            {
                "user_id": user_id,
                "access_token": data["access"],
                "refresh_token": refresh_token,
                "token_type": "Bearer",
            },
            status=status.HTTP_200_OK,
        )


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


class LogoutView(APIView):
    """主动退出：撤销当前设备会话并标记 trusted_device.is_revoked=true（ACCOUNTS-000003）。"""

    authentication_classes = [SparkJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "用户登出开始",
            extra={
                "action": "auth.logout",
                "path": request.path,
                "method": request.method,
                "request_id": request_id,
                "user_id": getattr(request.user, "id", None),
            },
        )
        claims = None
        if request.auth is not None:
            claims = DeviceSessionService._claims_from_validated_token(request.auth)
        DeviceSessionService.logout_current_session(
            user=request.user,
            request_id=request_id,
            claims=claims,
        )
        flow_logger.info(
            "用户登出成功",
            extra={
                "action": "auth.logout",
                "outcome": "success",
                "request_id": request_id,
                "user_id": getattr(request.user, "id", None),
            },
        )
        return success_response({}, msg="logout_success", code=0, status_code=status.HTTP_200_OK)


class CurrentSessionView(APIView):
    """Return latest account session for authenticated clients (cold-start refresh)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "获取当前会话开始",
            extra={
                "action": "auth.session.current",
                "path": request.path,
                "method": request.method,
                "request_id": request_id,
                "user_id": getattr(request.user, "id", None),
            },
        )
        payload = LoginService.build_current_session(user=request.user)
        flow_logger.info(
            "获取当前会话成功",
            extra={
                "action": "auth.session.current",
                "outcome": "success",
                "request_id": request_id,
                "user_id": payload.get("user_id"),
                "is_pro": payload.get("is_pro"),
            },
        )
        return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)