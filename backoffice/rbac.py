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
        ("menu:tasks", "异步任务看板", "menu", "/tasks", ""),
        ("menu:users", "用户管理", "menu", "/users", ""),
        ("menu:ai", "AI 场景配置", "menu", "/ai-config", ""),
        ("menu:ai:scenario", "AI 场景配置", "menu", "/ai-config/scenarios", "menu:ai"),
        ("menu:ai:models", "模型目录", "menu", "/ai-config/models", "menu:ai"),
        ("menu:ai:provider", "Provider 配置", "menu", "/ai-config/providers", "menu:ai"),
        ("menu:ai:trial", "试用期", "menu", "/ai-config/trials", "menu:ai"),
        ("menu:rbac", "权限管理", "menu", "/rbac", ""),
        ("menu:audit", "审计日志", "menu", "/audit", ""),
        ("button:user:status:update", "用户状态更新", "button", "", "menu:users"),
        ("button:ai:scenario:create", "AI场景新增", "button", "", "menu:ai:scenario"),
        ("button:ai:scenario:update", "AI场景更新", "button", "", "menu:ai"),
        ("button:ai:model:create", "模型目录新增", "button", "", "menu:ai:models"),
        ("button:ai:model:update", "模型目录更新", "button", "", "menu:ai:models"),
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
