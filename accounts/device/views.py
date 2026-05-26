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


# 设备注册接口视图
class DeviceRegisterView(APIView):
    """
    设备注册接口
    POST 请求地址：/api/v1/device/register/

    权限说明：
    1. 允许所有用户访问（未登录/已登录均可）
    2. 支持可选的 Bearer JWT 身份验证
       - 若 JWT 有效：注册的设备会绑定到当前登录用户
       - 若 JWT 无效/过期：不会返回 401 未授权，仅跳过用户绑定逻辑
    3. JWT 仅在 post 方法内解析，避免无效 token 直接拦截请求
    """

    # 权限控制：允许所有访问
    permission_classes = [AllowAny]
    # 关闭默认身份认证（手动处理 JWT）
    authentication_classes = []
    # 接口限流：匿名用户设备注册限流规则
    throttle_classes = [DeviceRegisterAnonThrottle]

    def post(self, request):
        """
        处理设备注册的 POST 请求
        :param request: 请求对象，包含设备注册参数、可选的 JWT 认证信息
        :return: 统一格式的成功响应
        """
        # 初始化用户为 None（未登录/无有效token时，设备不绑定用户）
        user = None
        try:
            # 手动初始化 JWT 认证器
            auth = JWTAuthentication()
            # 尝试从请求中解析 JWT 并认证用户
            result = auth.authenticate(request)
            # 认证成功：获取用户对象（token 为 JWT 令牌本身）
            if result is not None:
                user, _token = result
        except (InvalidToken, TokenError, AuthenticationFailed) as exc:
            # JWT 认证失败（无效/过期/格式错误）：记录调试日志，不中断注册流程
            flow_logger.debug(
                "device.register.optional_jwt_skip",
                extra={"action": "device.register", "reason": str(exc)},
            )

        # 序列化器校验请求参数（校验不通过直接抛出异常）
        serializer = DeviceRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 获取请求唯一 ID（用于日志追踪）
        request_id = getattr(request, "request_id", "") or ""
        # 获取前端显式传递的参数键集合
        explicit_keys = set(request.data.keys())

        # 调用设备服务层：执行设备注册逻辑
        out = DeviceService.register_device(
            user=user,                  # 绑定的用户（可为 None）
            data=serializer.validated_data,  # 校验后的合法参数
            explicit_keys=explicit_keys,      # 前端显式传入的字段
            request_id=request_id,      # 请求追踪 ID
        )

        # 返回统一格式的成功响应
        return success_response(
            data=out,
            msg="device_registered",
            code=0,
            status_code=status.HTTP_200_OK
        )
