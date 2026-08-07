# TASK-PERMISSION-000001 任务创建成员绑定权限优化工单

## 背景

2026-08-07 线上日志显示，客户端调用 `POST /api/v1/tasks/` 创建 AI 健康任务时返回 400：

```json
{
  "code": -1,
  "msg": "invalid_params",
  "data": {
    "member": ["member does not belong to current user"]
  }
}
```

请求中的 token 用户为 `user_id=265`，请求体传入 `member=10`。当前任务系统仍按 `member.user_id == request.user.id` 判断成员归属，而医疗档案模块已经升级为 `UserMemberBinding` 成员绑定和共享权限模型，因此共享成员、绑定成员会被任务系统误判为不属于当前用户。

## 目标

1. 任务系统统一使用 `MemberPermissionGate` 判断成员可见、可创建、可编辑权限。
2. `POST /api/v1/tasks/` 对 editor/admin/owner 绑定用户放行，对 viewer 或无绑定用户返回权限错误。
3. 任务列表、同步、AI 预查询、详情操作不得泄露无绑定成员任务。
4. 错误语义从通用 `invalid_params` 优化为明确的 `403 permission_denied` 或 `404 member_not_found`。

## 改造范围

| 文件 | 改造点 |
| --- | --- |
| `task_system/serializers.py` | `TaskSerializer.validate_member` 切换到 `MemberPermissionGate.require_create` |
| `task_system/views.py` | 任务查询统一按可访问成员过滤；更新、完成、取消增加编辑权限校验；权限错误转 403 |
| `task_system/tests_task_permissions.py` | 补充共享 editor 可创建、viewer 不可创建、陌生人不可见任务的回归测试 |

## 接口契约

### 创建任务

`POST /api/v1/tasks/`

- owner/admin/editor：允许创建任务。
- viewer：返回 `403`，`msg=permission_denied`，`data.code=member_permission_denied`。
- 无绑定或成员已删除：返回 `404`，`msg=member_not_found`。

### 查询任务

`GET /api/v1/tasks/` 与 `GET /api/v1/tasks/sync/`

- 默认仅返回当前用户可访问成员的任务。
- 传入 `member_id` 时，若当前用户不可访问该成员，返回 `404 member_not_found`。

### 变更任务状态

`PATCH /api/v1/tasks/{id}/`、`POST /api/v1/tasks/{id}/complete/`、`POST /api/v1/tasks/{id}/cancel/`

- 当前用户必须对任务成员具备编辑权限。
- 无任务访问权时返回 `404 task_not_found`。
- 有查看权但无编辑权时返回 `403 permission_denied`。

## 验收项

1. 共享 editor 用户对 owner 成员调用 `POST /api/v1/tasks/`，返回 `201 created`，并成功写入 `task` 与 `task_medical`。
2. 共享 viewer 用户调用同一创建接口，返回 `403 permission_denied`。
3. 无绑定用户调用列表和同步接口，看不到其他成员任务。
4. 无绑定用户指定 `member_id` 查询任务，返回 `404 member_not_found`。
5. 回归执行 `python manage.py test task_system.tests_task_permissions` 通过。
