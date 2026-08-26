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
from accounts.auth.serializers import (
    AppleLoginSerializer,
    DeviceLoginSerializer,
    PasswordLoginSerializer,
    TokenRefreshSerializer,
    WebAppleLoginSerializer,
    WebPhoneOTPRequestSerializer,
    WebPhoneOTPVerifySerializer,
)
from accounts.models import LoginAudit
from accounts.services.device_login_service import DeviceLoginService
from accounts.services.login_audit_service import LoginAuditService
from accounts.services.device_session_service import DeviceSessionService
from accounts.services.login_service import LoginService
from accounts.services.access_control_service import AccessControlService
from accounts.services.web_apple_login_service import WebAppleLoginService
from accounts.services.web_phone_login_service import WebPhoneLoginService
from accounts.services.web_session_service import WebSessionService
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
        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        user_agent = meta.get("HTTP_USER_AGENT", "") or ""

        try:
            return self._refresh_tokens(
                provided_refresh=provided_refresh,
                bundle_id=bundle_id,
                device_id=device_id,
                request_id=request_id,
            )
        except APIError as exc:
            LoginAuditService.write_failure_from_api_error(
                exc=exc,
                provider=LoginAudit.LoginProvider.DEVICE if device_id else LoginAudit.LoginProvider.PASSWORD,
                bundle_id=bundle_id,
                device_id=device_id,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                raw_claims={"failure_stage": "token_refresh"},
            )
            raise

    def _refresh_tokens(self, *, provided_refresh: str, bundle_id: str, device_id: str, request_id: str):
        try:
            refresh_claims = dict(RefreshToken(provided_refresh).payload)
        except Exception:
            flow_logger.warning(
                "刷新访问令牌失败",
                extra={"action": "auth.token.refresh", "outcome": "failed", "request_id": request_id, "reason": "token_not_valid"},
            )
            raise APIError("token_not_valid", code=40102, status_code=status.HTTP_401_UNAUTHORIZED)

        # Web session domain (CHAT-WEB-019B): dispatch by claim, never by
        # user-agent or request body. Web refresh must not touch device sessions.
        if WebSessionService.claims_conflict_session_classes(refresh_claims):
            raise APIError(
                WebSessionService.WEB_SESSION_CLASS_CONFLICT,
                code=40186,
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        if WebSessionService.claims_require_web_session(refresh_claims):
            user, session, _claims = WebSessionService.validate_refresh_request(
                refresh_token_str=provided_refresh,
            )
            tokens = WebSessionService.rotate_tokens_after_refresh(user=user, session=session)
            flow_logger.info(
                "刷新 Web 访问令牌成功",
                extra={
                    "action": "auth.token.refresh",
                    "outcome": "success",
                    "session_class": "web",
                    "request_id": request_id,
                    "user_id": user.id,
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
        username = (request.data.get("username") or "").strip()
        parsed = AccessControlService.parse_identifier_for_deny(username)
        AccessControlService.check(
            email=parsed.get("email", ""),
            phone=parsed.get("phone", ""),
            provider=LoginAudit.LoginProvider.PASSWORD,
            request_id=getattr(request, "request_id", "") or "",
            ip_address=request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")) or "",
            user_agent=request.META.get("HTTP_USER_AGENT", "") or "",
        )
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

        AccessControlService.check(
            user_id=user.id,
            email=user.email or "",
            provider=LoginAudit.LoginProvider.PASSWORD,
            request_id=getattr(request, "request_id", "") or "",
            ip_address=request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")) or "",
            user_agent=request.META.get("HTTP_USER_AGENT", "") or "",
        )

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

        try:
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
                device_secret=data.get("device_secret", "") or "",
                request_id=getattr(request, "request_id", "") or "",
            )
        except APIError as exc:
            LoginAuditService.write_failure_from_api_error(
                exc=exc,
                provider=LoginAudit.LoginProvider.APPLE,
                bundle_id=data.get("bundle_id", "") or "",
                device_id=data.get("device_id", "") or "",
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                raw_claims={
                    "failure_stage": "apple_login",
                    "apple_user_identifier": data.get("user", "") or "",
                },
            )
            raise

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


class WebAppleLoginView(APIView):
    """Chat Web Apple 独立登录入口（CHAT-WEB-019D）。

    与移动端 /auth/apple/login/ 完全隔离：只创建 AccountWebSession，
    签发 session_class=web 的 token，不进入设备会话域。
    """

    permission_classes = [AllowAny]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "Web Apple 登录接口请求开始",
            extra={"action": "auth.apple.web.login", "path": request.path, "method": request.method, "request_id": request_id},
        )
        serializer = WebAppleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        user_agent = meta.get("HTTP_USER_AGENT", "") or ""
        data = serializer.validated_data

        try:
            result = WebAppleLoginService.authenticate_apple_web_and_issue_tokens(
                identity_token=data["identity_token"],
                authorization_code=data.get("authorization_code", "") or "",
                nonce=data["nonce"],
                service_id=data["service_id"],
                redirect_uri=data.get("redirect_uri", "") or "",
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                user_identifier=data.get("user", "") or "",
                email=data.get("email", "") or "",
                full_name=data.get("full_name", "") or "",
            )
        except APIError as exc:
            LoginAuditService.write_failure_from_api_error(
                exc=exc,
                provider=LoginAudit.LoginProvider.APPLE,
                bundle_id=data.get("service_id", "") or "",
                device_id="",
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                raw_claims={
                    "failure_stage": "apple_web_login",
                    "channel": "web",
                    "apple_user_identifier": data.get("user", "") or "",
                },
            )
            raise

        flow_logger.info(
            "Web Apple 登录成功",
            extra={
                "action": "auth.apple.web.login",
                "outcome": "success",
                "request_id": request_id,
                "user_id": result.get("user_id"),
                "provider": "apple",
                "session_class": "web",
                "is_new_user": result.get("is_new_user", False),
            },
        )
        return success_response(result, msg="login_success", code=0, status_code=status.HTTP_200_OK)


class WebPhoneOTPRequestView(APIView):
    """Web 手机验证码请求入口（CHAT-WEB-020C）。使用服务端固定 Web Service ID，不接收移动字段。"""

    permission_classes = [AllowAny]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        serializer = WebPhoneOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""

        result = WebPhoneLoginService.request_otp(
            phone_number=serializer.validated_data["phone_number"],
            scene=serializer.validated_data.get("scene", "") or "login",
            ip_address=ip_address,
            request_id=request_id,
        )
        flow_logger.info(
            "auth.phone_otp.web.request.success",
            extra={
                "action": "auth.phone_otp.web.request",
                "outcome": "success",
                "request_id": request_id,
                "otp_id": result.get("otp_id"),
            },
        )
        return success_response(result, msg="otp_sent", code=0, status_code=status.HTTP_200_OK)


class WebPhoneOTPVerifyView(APIView):
    """Web 手机验证码校验入口（CHAT-WEB-020C）。只签发 AccountWebSession token，不进入设备会话域。"""

    permission_classes = [AllowAny]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        serializer = WebPhoneOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        user_agent = meta.get("HTTP_USER_AGENT", "") or ""

        try:
            result = WebPhoneLoginService.verify_and_issue_tokens(
                otp_id=serializer.validated_data["otp_id"],
                phone_number=serializer.validated_data["phone_number"],
                code=serializer.validated_data["code"],
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
        except APIError as exc:
            if exc.code not in {40043}:
                LoginAuditService.write_failure_from_api_error(
                    exc=exc,
                    provider=LoginAudit.LoginProvider.PHONE_OTP,
                    bundle_id="",
                    device_id="",
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    raw_claims={"failure_stage": "phone_otp_web_verify", "channel": "web"},
                )
            raise
        flow_logger.info(
            "auth.phone_otp.web.verify.success",
            extra={
                "action": "auth.phone_otp.web.verify",
                "outcome": "success",
                "request_id": request_id,
                "user_id": result.get("user_id"),
                "otp_id": result.get("otp_id"),
                "session_class": result.get("session_class"),
            },
        )
        return success_response(result, msg="otp_verified", code=0, status_code=status.HTTP_200_OK)


class DeviceLoginView(APIView):
    """设备游客账户登录：device_id + device_secret。"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "设备登录接口请求开始",
            extra={
                "action": "auth.device.login",
                "path": request.path,
                "method": request.method,
                "request_id": request_id,
            },
        )
        serializer = DeviceLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        user_agent = meta.get("HTTP_USER_AGENT", "") or ""

        try:
            result = DeviceLoginService.authenticate_and_issue_tokens(
                bundle_id=data["bundle_id"],
                device_id=data["device_id"],
                device_secret=data["device_secret"],
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                attestation=data.get("attestation", "") or "",
            )
        except APIError as exc:
            LoginAuditService.write_failure_from_api_error(
                exc=exc,
                provider=LoginAudit.LoginProvider.DEVICE,
                bundle_id=data.get("bundle_id", "") or "",
                device_id=data.get("device_id", "") or "",
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                raw_claims={"failure_stage": "device_login"},
            )
            raise
        flow_logger.info(
            "设备登录成功",
            extra={
                "action": "auth.device.login",
                "outcome": "success",
                "request_id": request_id,
                "user_id": result.get("user_id"),
                "account_resolution": result.get("account_resolution"),
                "is_new_user": result.get("is_new_user", False),
            },
        )
        return success_response(result, msg="login_success", code=0, status_code=status.HTTP_200_OK)


class LogoutView(APIView):
    """主动退出：按 token claim 分派会话域（CHAT-WEB-019）。

    Web token（web_session_id + session_class=web）只撤销当前 AccountWebSession；
    设备 token 沿用单设备退出语义；两者互不影响。
    """

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
        if claims and WebSessionService.claims_require_web_session(claims):
            WebSessionService.logout_current_session(
                user=request.user,
                request_id=request_id,
                claims=claims,
            )
        else:
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
                "session_class": "web" if (claims and WebSessionService.claims_require_web_session(claims)) else "device",
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
