from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from app_version.models import AppVersionConfig, UpdateActionLog, VersionCheckLog
from app_version.serializers import UpdateActionRequestSerializer, VersionCheckRequestSerializer
from app_version.utils import get_client_ip, is_client_older, should_show_gradual_release
from common.response import success_response


# ------------------------------
# 限流配置
# ------------------------------

class VersionCheckThrottle(AnonRateThrottle):
    """版本检查接口限流：匿名用户每小时 10060 次"""
    rate = "10060/hour"


class UpdateActionThrottle(AnonRateThrottle):
    """更新行为上报接口限流：匿名用户每小时 100120 次"""
    rate = "100120/hour"


# ------------------------------
# 工具方法
# ------------------------------

def _optional_user(request):
    """
    尝试从请求头解析登录用户
    支持 JWT Token，解析失败返回 None
    """
    try:
        result = JWTAuthentication().authenticate(request)
        if result is not None:
            return result[0]
    except (InvalidToken, TokenError, AuthenticationFailed):
        return None
    return None


# ------------------------------
# 版本检查接口
# ------------------------------

class VersionCheckAPI(APIView):
    """
    APP 版本检查接口
    功能：查询是否需要更新、是否强制更新、灰度发布判断、记录检查日志
    """
    permission_classes = [AllowAny]  # 允许所有人访问
    authentication_classes = []  # 不强制登录
    throttle_classes = [VersionCheckThrottle]  # 限流

    def get(self, request):
        # 1. 校验请求参数
        serializer = VersionCheckRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 2. 提取请求参数
        platform = data["platform"]  # 平台：iOS / Android
        bundle_id = data.get("bundle_id") or ""  # 包名
        channel = data.get("channel") or AppVersionConfig.Channel.PRODUCTION  # 渠道
        current_version = data["version"]  # 当前版本号
        current_build = data.get("build") or ""  # 当前构建号
        device_id = data["device_id"]  # 设备唯一标识

        # 3. 查询匹配的版本配置（优先匹配 bundle_id，再匹配空 bundle_id）
        config_qs = AppVersionConfig.objects.filter(
            platform=platform,
            channel=channel,
            is_active=True
        )

        # 先按 bundle_id 精确匹配
        config = (
            config_qs.filter(bundle_id=bundle_id).order_by("-created_at", "-id").first()
            if bundle_id
            else None
        )

        # 无精确匹配 → 使用通用配置（bundle_id 为空）
        if config is None:
            config = config_qs.filter(bundle_id="").order_by("-created_at", "-id").first()

        # 4. 初始化版本判断结果
        has_update = False
        force_update = False
        reason = "no_config"

        # 5. 有配置时，判断是否需要更新
        if config is not None:
            reason = "latest"
            # 判断是否在灰度发布范围内
            if config.enable_gradual_release and not should_show_gradual_release(
                    device_id=device_id,
                    bundle_id=bundle_id,
                    current_version=current_version,
                    percentage=config.gradual_release_percentage,
                    min_version=config.gradual_release_min_version,
            ):
                reason = "outside_gradual_release"
            else:
                # 比较版本号：判断是否有新版本
                has_update = is_client_older(
                    current_version, config.latest_version,
                    current_build, config.latest_build
                )
                reason = "update_available" if has_update else "latest"

                # 判断是否强制更新
                if has_update and config.force_update_min_version:
                    force_update = is_client_older(
                        current_version,
                        config.force_update_min_version,
                        current_build,
                        config.force_update_min_build,
                    )

        # 6. 记录版本检查日志（原子操作）
        user = _optional_user(request)
        with transaction.atomic():
            check_log = VersionCheckLog.objects.create(
                platform=platform,
                bundle_id=bundle_id,
                channel=channel,
                current_version=current_version,
                current_build=current_build,
                device_id=device_id,
                system_version=data.get("system_version") or "",
                user=user,
                config=config,
                has_update=has_update,
                force_update=force_update,
                latest_version=config.latest_version if config and has_update else "",
                latest_build=config.latest_build if config and has_update else "",
                decision_reason=reason,
                ip_address=get_client_ip(request),
                request_id=getattr(request, "request_id", "") or "",
            )

        # 7. 无更新 / 无配置 → 返回无更新
        if not has_update or config is None:
            messages = {
                "no_config": "暂无版本信息",
                "outside_gradual_release": "当前不在灰度发布范围内",
                "latest": "当前已是最新版本",
            }
            return success_response(
                {
                    "checkLogId": check_log.id,
                    "hasUpdate": False,
                    "message": messages.get(reason, "当前已是最新版本"),
                },
                status_code=status.HTTP_200_OK,
            )

        # 8. 有更新 → 返回完整更新信息
        return success_response(
            {
                "checkLogId": check_log.id,
                "hasUpdate": True,
                "latestVersion": config.latest_version,
                "latestBuild": config.latest_build,
                "forceUpdate": force_update,
                "updateTitle": config.update_title,
                "updateMessage": config.update_message,
                "downloadUrl": config.download_url,
                "releaseNotes": config.release_notes,
            },
            status_code=status.HTTP_200_OK,
        )


# ------------------------------
# 用户更新行为上报接口
# ------------------------------

class UpdateActionAPI(APIView):
    """
    APP 更新行为上报接口
    功能：记录用户点击更新、稍后、关闭、弹窗展示等行为
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [UpdateActionThrottle]

    def post(self, request):
        # 1. 校验请求参数
        serializer = UpdateActionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 2. 尝试根据 check_log_id 找到对应的版本检查记录
        check_log = None
        check_log_id = data.get("check_log_id")
        if check_log_id:
            check_log = VersionCheckLog.objects.filter(id=check_log_id).first()

        # 3. 找不到日志 → 按设备/平台/包名 查找最近1小时的检查记录
        if check_log is None:
            device_id = data.get("device_id") or ""
            platform = data.get("platform") or ""
            bundle_id = data.get("bundle_id") or ""
            qs = VersionCheckLog.objects.filter(
                checked_at__gte=timezone.now() - timedelta(hours=1)
            )
            if device_id:
                qs = qs.filter(device_id=device_id)
            if platform:
                qs = qs.filter(platform=platform)
            if bundle_id:
                qs = qs.filter(bundle_id=bundle_id)
            check_log = qs.order_by("-checked_at", "-id").first()

        # 4. 找到日志 → 创建行为记录
        if check_log is not None:
            user = check_log.user or _optional_user(request)
            UpdateActionLog.objects.create(
                check_log=check_log,
                user=user,
                action=data["action"],
                device_id=data.get("device_id") or check_log.device_id,
                platform=data.get("platform") or check_log.platform,
                request_id=getattr(request, "request_id", "") or "",
            )

        # 5. 统一返回成功
        return success_response(
            {"success": True},
            status_code=status.HTTP_200_OK
        )