from django.conf import settings
from django.db import models


# 应用版本配置表：存储 iOS/Android 各渠道的版本更新规则
class AppVersionConfig(models.Model):
    # 平台枚举
    class Platform(models.TextChoices):
        IOS = "iOS", "iOS"  # iOS 平台
        ANDROID = "Android", "Android"  # Android 平台

    # 发布渠道枚举
    class Channel(models.TextChoices):
        PRODUCTION = "production", "Production"  # 生产环境
        TESTFLIGHT = "testflight", "TestFlight"  # TestFlight 测试
        INTERNAL = "internal", "Internal"  # 内部测试

    # 基础配置
    platform = models.CharField(max_length=20, choices=Platform.choices, db_index=True, verbose_name="平台")
    bundle_id = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="包名/BundleID")
    channel = models.CharField(max_length=32, choices=Channel.choices, default=Channel.PRODUCTION, db_index=True,
                               verbose_name="渠道")

    # 最新版本信息
    latest_version = models.CharField(max_length=50, verbose_name="最新版本号")
    latest_build = models.CharField(max_length=50, blank=True, default="", verbose_name="最新构建号")

    # 强制更新配置
    force_update_min_version = models.CharField(max_length=50, blank=True, default="", verbose_name="强制更新最低版本")
    force_update_min_build = models.CharField(max_length=50, blank=True, default="", verbose_name="强制更新最低构建号")

    # 更新弹窗文案
    update_title = models.CharField(max_length=200, verbose_name="更新标题")
    update_message = models.TextField(verbose_name="更新提示内容")
    release_notes = models.TextField(blank=True, default="", verbose_name="发布说明")

    # 下载与发布
    download_url = models.URLField(max_length=512, verbose_name="下载地址")
    enable_gradual_release = models.BooleanField(default=False, verbose_name="是否开启灰度发布")
    gradual_release_percentage = models.PositiveSmallIntegerField(default=100, verbose_name="灰度发布比例(%)")
    gradual_release_min_version = models.CharField(max_length=50, blank=True, default="",
                                                   verbose_name="灰度生效最低版本")

    # 状态
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="是否启用")

    # 操作与时间
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="created_app_version_configs",
        on_delete=models.SET_NULL,
        verbose_name="创建人"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["-created_at", "-id"]  # 默认排序：按创建时间倒序
        indexes = [
            # 联合索引：版本检查高频查询条件
            models.Index(fields=["platform", "bundle_id", "channel", "is_active"]),
            models.Index(fields=["is_active", "created_at"]),
        ]
        verbose_name = "应用版本配置"
        verbose_name_plural = "应用版本配置"

    def __str__(self):
        bundle = self.bundle_id or "*"
        return f"{self.platform}/{bundle}/{self.channel} {self.latest_version}"


# 版本检查日志：记录客户端每一次的版本查询请求
class VersionCheckLog(models.Model):
    platform = models.CharField(max_length=20, db_index=True, verbose_name="平台")
    bundle_id = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="包名/BundleID")
    channel = models.CharField(max_length=32, blank=True, default="production", db_index=True, verbose_name="渠道")

    # 客户端当前版本
    current_version = models.CharField(max_length=50, verbose_name="当前版本")
    current_build = models.CharField(max_length=50, blank=True, default="", verbose_name="当前构建号")

    # 设备信息
    device_id = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="设备ID")
    system_version = models.CharField(max_length=50, blank=True, default="", verbose_name="系统版本")

    # 用户与关联配置
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="version_check_logs",
        on_delete=models.SET_NULL,
        verbose_name="用户"
    )
    config = models.ForeignKey(
        AppVersionConfig,
        null=True,
        blank=True,
        related_name="check_logs",
        on_delete=models.SET_NULL,
        verbose_name="关联版本配置"
    )

    # 检查结果
    has_update = models.BooleanField(default=False, db_index=True, verbose_name="是否有更新")
    force_update = models.BooleanField(default=False, db_index=True, verbose_name="是否强制更新")
    latest_version = models.CharField(max_length=50, blank=True, default="", verbose_name="返回的最新版本")
    latest_build = models.CharField(max_length=50, blank=True, default="", verbose_name="返回的最新构建号")

    # 决策与请求信息
    decision_reason = models.CharField(max_length=64, blank=True, default="", verbose_name="版本决策原因")
    ip_address = models.CharField(max_length=64, blank=True, default="", verbose_name="IP地址")
    request_id = models.CharField(max_length=64, blank=True, default="", verbose_name="请求ID")
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="检查时间")

    class Meta:
        ordering = ["-checked_at", "-id"]
        indexes = [
            models.Index(fields=["platform", "checked_at"]),
            models.Index(fields=["bundle_id", "device_id", "checked_at"]),
            models.Index(fields=["has_update", "force_update"]),
        ]
        verbose_name = "版本检查日志"
        verbose_name_plural = "版本检查日志"


# 更新行为日志：记录用户对更新弹窗的操作（点击更新、稍后、关闭等）
class UpdateActionLog(models.Model):
    # 用户行为枚举
    class Action(models.TextChoices):
        FORCE_UPDATE_SHOWN = "force_update_shown", "Force update shown"  # 强制更新弹窗展示
        OPTIONAL_UPDATE_SHOWN = "optional_update_shown", "Optional update shown"  # 可选更新弹窗展示
        UPDATE_CLICKED = "update_clicked", "Update clicked"  # 点击更新
        LATER_CLICKED = "later_clicked", "Later clicked"  # 点击稍后
        DISMISSED = "dismissed", "Dismissed"  # 关闭弹窗

    # 关联检查日志
    check_log = models.ForeignKey(VersionCheckLog, related_name="actions", on_delete=models.CASCADE,
                                  verbose_name="关联检查日志")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="version_update_actions",
        on_delete=models.SET_NULL,
        verbose_name="用户"
    )

    # 行为信息
    action = models.CharField(max_length=50, choices=Action.choices, db_index=True, verbose_name="用户行为")
    device_id = models.CharField(max_length=255, blank=True, default="", verbose_name="设备ID")
    platform = models.CharField(max_length=20, blank=True, default="", verbose_name="平台")
    request_id = models.CharField(max_length=64, blank=True, default="", verbose_name="请求ID")
    action_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="行为时间")

    class Meta:
        ordering = ["-action_at", "-id"]
        indexes = [
            models.Index(fields=["action", "action_at"]),
            models.Index(fields=["user", "action_at"]),
        ]
        verbose_name = "更新行为日志"
        verbose_name_plural = "更新行为日志"