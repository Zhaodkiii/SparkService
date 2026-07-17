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
        ("menu:conversations", "对话", "menu", "/conversations", ""),
        ("menu:conversations:users", "用户对话", "menu", "/conversations/users", "menu:conversations"),
        ("menu:medical_data", "医疗数据", "menu", "/medical-data", ""),
        ("menu:medical_data:users", "用户医疗数据", "menu", "/medical-data/users", "menu:medical_data"),
        ("menu:medical_data:quality", "数据质检", "menu", "/medical-data/quality", "menu:medical_data"),
        ("menu:medical_data:attachments", "附件与识别", "menu", "/medical-data/attachments", "menu:medical_data"),
        ("menu:medical_data:analytics", "医疗数据统计", "menu", "/medical-data/analytics", "menu:medical_data"),
        ("menu:articles", "文章模块", "menu", "/articles", ""),
        ("menu:articles:overview", "文章总览", "menu", "/articles/overview", "menu:articles"),
        ("menu:articles:list", "文章管理", "menu", "/articles/list", "menu:articles"),
        ("menu:articles:categories", "分类管理", "menu", "/articles/categories", "menu:articles"),
        ("menu:articles:tags", "标签管理", "menu", "/articles/tags", "menu:articles"),
        ("menu:articles:locales", "多语言管理", "menu", "/articles/locales", "menu:articles"),
        ("menu:articles:analytics", "阅读数据", "menu", "/articles/analytics", "menu:articles"),
        ("menu:articles:compliance", "来源合规", "menu", "/articles/compliance", "menu:articles"),
        ("menu:articles:recycle_bin", "回收站", "menu", "/articles/recycle-bin", "menu:articles"),
        ("content.article.read", "查看文章", "api", "", "menu:articles:list"),
        ("content.article.create", "创建文章", "button", "", "menu:articles:list"),
        ("content.article.update", "编辑文章", "button", "", "menu:articles:list"),
        ("content.article.delete", "删除文章", "button", "", "menu:articles:list"),
        ("content.article.publish", "发布文章", "button", "", "menu:articles:list"),
        ("content.article.offline", "下架文章", "button", "", "menu:articles:list"),
        ("content.article.archive", "归档文章", "button", "", "menu:articles:list"),
        ("content.version.read", "查看文章版本", "api", "", "menu:articles:list"),
        ("content.version.rollback", "回滚文章版本", "button", "", "menu:articles:list"),
        ("content.category.read", "查看文章分类", "api", "", "menu:articles:categories"),
        ("content.category.create", "创建文章分类", "button", "", "menu:articles:categories"),
        ("content.category.update", "编辑文章分类", "button", "", "menu:articles:categories"),
        ("content.category.delete", "删除文章分类", "button", "", "menu:articles:categories"),
        ("content.tag.read", "查看文章标签", "api", "", "menu:articles:tags"),
        ("content.tag.create", "创建文章标签", "button", "", "menu:articles:tags"),
        ("content.tag.update", "编辑文章标签", "button", "", "menu:articles:tags"),
        ("content.tag.delete", "删除文章标签", "button", "", "menu:articles:tags"),
        ("content.tag.merge", "合并文章标签", "button", "", "menu:articles:tags"),
        ("api:medical_data:user:list", "医疗数据用户列表", "api", "", "menu:medical_data:users"),
        ("api:medical_data:member:list", "医疗数据成员列表", "api", "", "menu:medical_data:users"),
        ("api:medical_data:member:complete", "成员医疗数据总览", "api", "", "menu:medical_data:users"),
        ("api:medical_data:resource:detail", "医疗资源详情", "api", "", "menu:medical_data:users"),
        ("button:medical_data:raw_json:view", "查看医疗原始 JSON", "button", "", "menu:medical_data:users"),
        ("button:medical_data:attachment:view", "预览医疗附件", "button", "", "menu:medical_data:users"),
        ("button:medical_data:attachment:download", "下载医疗附件", "button", "", "menu:medical_data:users"),
        ("button:medical_data:sensitive:view", "查看医疗未脱敏字段", "button", "", "menu:medical_data:users"),
        ("button:medical_data:export", "医疗数据导出", "button", "", "menu:medical_data:users"),
        ("button:user:status:update", "用户状态更新", "button", "", "menu:users"),
        ("button:user:pro:grant", "用户发放 Pro", "button", "", "menu:users"),
        ("button:user:pro:recycle", "用户回收 Pro", "button", "", "menu:users"),
        ("button:user:device:revoke", "设备吊销更新", "button", "", "menu:users:devices"),
        ("button:user:deactivation:cancel", "注销单取消", "button", "", "menu:users:deactivations"),
        ("button:user:deactivation:retry", "注销单重试", "button", "", "menu:users:deactivations"),
        ("button:tasks:manager:control", "异步任务启停", "button", "", "menu:tasks:manager"),
        ("button:notification:send", "发送通知", "button", "", "menu:notifications:users"),
        ("button:notification:template:edit", "编辑模板", "button", "", "menu:notifications:templates"),
        ("button:notification:sms:query_send_details", "查询短信回执", "button", "", "menu:notifications:records:sms"),
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
        ("button:ai:trial:grant", "试用发放权限", "button", "", "menu:ai:trial"),
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
