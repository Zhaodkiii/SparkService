from collections import defaultdict

from backoffice.models import AdminPermission, AdminRole, AdminUserRole


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
    role, _ = AdminRole.objects.get_or_create(
        code="super_admin",
        defaults={"name": "Super Admin", "description": "Full access"},
    )

    defaults = [
        ("menu:dashboard", "仪表盘", "menu", "/dashboard", ""),
        ("menu:tasks", "异步任务", "menu", "/tasks", ""),
        ("menu:tasks:dashboard", "异步任务看板", "menu", "/tasks", "menu:tasks"),
        ("menu:tasks:manager", "异步任务管理", "menu", "/tasks/manager", "menu:tasks"),
        ("menu:users", "用户管理", "menu", "/users", ""),
        ("menu:users:list", "用户管理", "menu", "/users", "menu:users"),
        ("menu:users:devices", "设备管理", "menu", "/users/devices", "menu:users"),
        ("menu:users:deactivations", "注销管理", "menu", "/users/deactivations", "menu:users"),
        ("menu:notifications", "通知中心", "menu", "/notifications", ""),
        ("menu:notifications:users", "通知用户列表", "menu", "/notifications/users", "menu:notifications"),
        ("menu:notifications:templates", "通知模板", "menu", "/notifications/templates", "menu:notifications"),
        ("menu:notifications:campaigns", "发送活动", "menu", "/notifications/campaigns", "menu:notifications"),
        ("menu:notifications:apns", "APNs发送记录", "menu", "/notifications/apns", "menu:notifications"),
        ("menu:notifications:sms", "短信发送记录", "menu", "/notifications/sms", "menu:notifications"),
        ("menu:notifications:email", "邮箱发送记录", "menu", "/notifications/email", "menu:notifications"),
        ("menu:version", "版本控制", "menu", "/version", ""),
        ("menu:version:configs", "版本配置", "menu", "/version/configs", "menu:version"),
        ("menu:version:logs", "检查日志", "menu", "/version/logs", "menu:version"),
        ("menu:ai", "AI 场景配置", "menu", "/ai-config", ""),
        ("menu:ai:scenario", "AI 场景配置", "menu", "/ai-config/scenarios", "menu:ai"),
        ("menu:ai:models", "模型目录", "menu", "/ai-config/models", "menu:ai"),
        ("menu:ai:small_tasks", "AI 小任务", "menu", "/ai-config/small-tasks", "menu:ai"),
        ("menu:ai:provider", "Provider 配置", "menu", "/ai-config/providers", "menu:ai"),
        ("menu:ai:trial", "试用期", "menu", "/ai-config/trials", "menu:ai"),
        ("menu:rbac", "权限管理", "menu", "/rbac", ""),
        ("menu:audit", "审计日志", "menu", "/audit", ""),
        ("button:user:status:update", "用户状态更新", "button", "", "menu:users"),
        ("button:user:device:revoke", "设备吊销更新", "button", "", "menu:users:devices"),
        ("button:user:deactivation:cancel", "注销单取消", "button", "", "menu:users:deactivations"),
        ("button:user:deactivation:retry", "注销单重试", "button", "", "menu:users:deactivations"),
        ("button:tasks:manager:control", "异步任务启停", "button", "", "menu:tasks:manager"),
        ("button:notification:send", "发送通知", "button", "", "menu:notifications:users"),
        ("button:notification:template:edit", "编辑模板", "button", "", "menu:notifications:templates"),
        ("button:version:config:create", "版本配置新增", "button", "", "menu:version:configs"),
        ("button:version:config:update", "版本配置更新", "button", "", "menu:version:configs"),
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
        ("button:rbac:role:assign", "角色分配", "button", "", "menu:rbac"),
    ]

    from backoffice.models import AdminPermission, AdminRolePermission

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
