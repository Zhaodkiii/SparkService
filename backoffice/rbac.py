from collections import defaultdict
from django.db.models import Q

from backoffice.models import AdminPermission, AdminRole, AdminUserRole, AdminRolePermission


def get_user_role_codes(user_id: int) -> list[str]:
    return list(
        AdminUserRole.objects.filter(user_id=user_id, role__is_active=True)
        .select_related("role")
        .values_list("role__code", flat=True)
        .distinct()
    )


def get_user_permission_codes(user_id: int) -> list[str]:
    return list(
        AdminPermission.objects.filter(
            permission_roles__role__role_users__user_id=user_id,
            permission_roles__role__is_active=True,
            is_active=True,
        )
        .values_list("code", flat=True)
        .distinct()
    )


def has_permission_code(user_id: int, code: str) -> bool:
    if not code:
        return True
    return AdminPermission.objects.filter(
        code=code,
        is_active=True,
        permission_roles__role__role_users__user_id=user_id,
        permission_roles__role__is_active=True,
    ).exists()


def get_user_menu_tree(user_id: int) -> list[dict]:
    menu_rows = list(
        AdminPermission.objects.filter(
            permission_type=AdminPermission.PermissionType.MENU,
            is_active=True,
            permission_roles__role__role_users__user_id=user_id,
            permission_roles__role__is_active=True,
        )
        .values("code", "name", "path", "parent_code")
        .distinct()
    )

    grouped = defaultdict(list)
    index = {}
    for row in menu_rows:
        node = {
            "code": row["code"],
            "name": row["name"],
            "path": row["path"],
            "children": [],
        }
        index[row["code"]] = node
        grouped[row["parent_code"]].append(node)

    for code, node in index.items():
        node["children"] = grouped.get(code, [])

    return grouped.get("", [])


def bootstrap_admin_permissions() -> None:
    AdminPermission.objects.filter(
        Q(code__contains="medical_data") | Q(code__contains="quick_questions") | Q(code__startswith="content.") | Q(code__startswith="menu:articles") | Q(code__startswith="menu:conversations") | Q(code__startswith="menu:version") | Q(code__startswith="menu:subscriptions") | Q(code__startswith="button:subscription:") | Q(code__startswith="button:version:")
    ).update(is_active=False)
    role, _ = AdminRole.objects.get_or_create(
        code="super_admin",
        defaults={"name": "Super Admin", "description": "Full access"},
    )

    defaults = [
        ("diary_presets.sync_template", "整本模板同步生产", "button", "", "menu:content:templates"),
        ("font_library.sync_fontfamily", "字体同步生产", "button", "", "menu:content:fonts"),
        ("font_library.view_fontfamily", "查看字体", "button", "", "menu:content:fonts"),
        ("font_library.change_fontfamily", "编辑字体", "button", "", "menu:content:fonts"),
        ("font_library.upload_fontfamily", "上传字体", "button", "", "menu:content:fonts"),
        ("font_library.publish_fontfamily", "发布字体", "button", "", "menu:content:fonts"),
        ("font_library.takedown_fontfamily", "上下架字体", "button", "", "menu:content:fonts"),

        ("menu:content", "内容资源", "menu", "/content", ""),
        ("menu:content:templates", "模板管理", "menu", "/content/templates", "menu:content"),
        ("menu:content:stickers", "贴纸管理", "menu", "/content/stickers", "menu:content"),
        ("menu:content:backgrounds", "背景管理", "menu", "/content/backgrounds", "menu:content"),
        ("menu:content:fonts", "字体管理", "menu", "/content/fonts", "menu:content"),

        ("menu:dashboard", "仪表盘", "menu", "/dashboard", ""),
        ("menu:tasks", "异步任务", "menu", "/tasks", ""),
        ("menu:tasks:dashboard", "异步任务看板", "menu", "/tasks", "menu:tasks"),
        ("menu:tasks:manager", "异步任务管理", "menu", "/tasks/manager", "menu:tasks"),
        ("menu:users", "用户管理", "menu", "/users", ""),
        ("menu:users:list", "用户管理", "menu", "/users", "menu:users"),
        ("menu:users:devices", "设备管理", "menu", "/users/devices", "menu:users"),
        ("menu:users:deactivations", "注销管理", "menu", "/users/deactivations", "menu:users"),
        ("menu:users:blacklist", "黑名单管理", "menu", "/users/blacklist", "menu:users"),
        ("menu:notifications", "通知中心", "menu", "/notifications", ""),
        ("menu:notifications:overview", "总览", "menu", "/notifications/overview", "menu:notifications"),
        ("menu:notifications:users", "通知用户列表", "menu", "/notifications/users", "menu:notifications"),
        ("menu:notifications:templates", "通知模板", "menu", "/notifications/templates", "menu:notifications"),
        ("menu:notifications:campaigns", "发送活动", "menu", "/notifications/campaigns", "menu:notifications"),
        ("menu:notifications:records", "发送记录", "menu", "/notifications/records", "menu:notifications"),
        ("menu:notifications:records:all", "全渠道记录", "menu", "/notifications/records/all", "menu:notifications:records"),
        ("menu:notifications:records:apns", "APNs发送记录", "menu", "/notifications/apns", "menu:notifications:records"),
        ("menu:notifications:records:sms", "短信发送记录", "menu", "/notifications/sms", "menu:notifications:records"),
        ("menu:notifications:records:email", "邮箱发送记录", "menu", "/notifications/email", "menu:notifications:records"),
        ("menu:notifications:suppressions", "异常与抑制", "menu", "/notifications/suppressions", "menu:notifications"),
        ("menu:notifications:analytics", "统计分析", "menu", "/notifications/analytics", "menu:notifications"),
        ("menu:notifications:channel_settings", "渠道设置", "menu", "/notifications/channel-settings", "menu:notifications"),
        ("menu:ai", "AI 场景配置", "menu", "/ai-config", ""),
        ("menu:ai:scenario", "AI 场景配置", "menu", "/ai-config/scenarios", "menu:ai"),
        ("menu:ai:models", "模型目录", "menu", "/ai-config/models", "menu:ai"),
        ("menu:ai:small_tasks", "AI 小任务", "menu", "/ai-config/small-tasks", "menu:ai"),
        ("menu:ai:provider", "Provider 配置", "menu", "/ai-config/providers", "menu:ai"),
        ("menu:ai:trial", "试用期", "menu", "/ai-config/trials", "menu:ai"),
        ("menu:rbac", "权限管理", "menu", "/rbac", ""),
        ("menu:audit", "审计日志", "menu", "/audit", ""),
        ("menu:audit:operator", "操作员日志", "menu", "/audit/admin", "menu:audit"),
        ("menu:audit:system", "系统日志", "menu", "/audit/system", "menu:audit"),
        ("audit:operator:list", "查看操作员日志", "api", "/api/admin/v1/audit/logs/", ""),
        ("audit:system:list", "查看系统日志", "api", "/api/admin/v1/audit/system-logs/", ""),
        ("audit:system:detail", "查看系统日志详情", "api", "/api/admin/v1/audit/system-logs/detail/", ""),
        ("audit:system:raw", "查看系统日志原文", "api", "/api/admin/v1/audit/system-logs/detail/", ""),
        ("audit:system:login", "查看登录日志", "api", "/api/admin/v1/audit/login-logs/", ""),
        ("button:user:status:update", "用户状态更新", "button", "", "menu:users"),
        ("button:user:pro:grant", "用户发放 Pro", "button", "", "menu:users"),
        ("button:user:pro:recycle", "用户回收 Pro", "button", "", "menu:users"),
        ("button:user:device:revoke", "设备吊销更新", "button", "", "menu:users:devices"),
        ("button:user:deactivation:cancel", "注销单取消", "button", "", "menu:users:deactivations"),
        ("button:user:deactivation:retry", "注销单重试", "button", "", "menu:users:deactivations"),
        ("button:user:blacklist:manage", "黑名单管理", "button", "", "menu:users:blacklist"),
        ("button:tasks:manager:control", "异步任务启停", "button", "", "menu:tasks:manager"),
        ("button:notification:send", "发送通知", "button", "", "menu:notifications:users"),
        ("button:notification:template:edit", "编辑模板", "button", "", "menu:notifications:templates"),
        ("button:notification:sms:query_send_details", "查询短信回执", "button", "", "menu:notifications:records:sms"),
        ("button:ai:scenario:create", "AI场景新增", "button", "", "menu:ai:scenario"),
        ("button:ai:scenario:update", "AI场景更新", "button", "", "menu:ai"),
        ("button:ai:model:create", "模型目录新增", "button", "", "menu:ai:models"),
        ("button:ai:model:update", "模型目录更新", "button", "", "menu:ai:models"),
        ("button:ai:small_task:create", "AI小任务新增", "button", "", "menu:ai:small_tasks"),
        ("button:ai:small_task:update", "AI小任务更新", "button", "", "menu:ai:small_tasks"),
        ("button:ai:provider:create", "AI供应商新增", "button", "", "menu:ai:provider"),
        ("button:ai:provider:update", "AI供应商更新", "button", "", "menu:ai"),
        ("button:ai:trial:approve", "试用通过", "button", "", "menu:ai:trial"),
        ("button:ai:trial:reject", "试用拒绝", "button", "", "menu:ai:trial"),
        ("button:ai:trial:recycle", "试用回收权限", "button", "", "menu:ai:trial"),
        ("button:ai:trial:grant", "试用发放权限", "button", "", "menu:ai:trial"),
        ("button:rbac:role:assign", "角色分配", "button", "", "menu:rbac"),
    ]


    defaults += [(f'support_center.{code}', name, 'api', '', '') for code,name in [('view_ticket','查看反馈工单'),('view_all_tickets','查看全部反馈'),('reply_ticket','回复反馈'),('assign_ticket','分派反馈'),('close_ticket','关闭反馈'),('reopen_ticket','重开反馈'),('view_contact','查看反馈联系方式'),('redact_content','隐藏反馈内容'),('edit_help','编辑帮助'),('publish_help','发布帮助'),('manage_config','配置反馈服务')]]
    for code, name, ptype, path, parent_code in defaults:
        permission, _ = AdminPermission.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "permission_type": ptype,
                "path": path,
                "parent_code": parent_code,
                "is_active": True,
            },
        )
        AdminRolePermission.objects.get_or_create(role=role, permission=permission)
