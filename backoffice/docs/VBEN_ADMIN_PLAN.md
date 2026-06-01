# SparkService + Vue Vben Admin 实施计划

## 1. 项目目标

使用 Vue Vben Admin 构建 `SparkService` 后台管理系统，覆盖运营、配置、风控、审计四类场景，形成“管理端前后端分离”架构。

## 2. 架构设计

- 管理前端：Vue 3 + TypeScript + Vue Vben Admin
- 管理后端：Django + DRF（新增 `/api/admin/v1/*`）
- 鉴权：复用 JWT，管理接口增加 `AdminOnlyPermission`（`is_staff` 或 `is_superuser`）
- 数据层：复用现有 MySQL 模型（accounts/chat_sync/medical/file_manager/ai_config）
- 任务层：复用 Celery，后续加入后台任务监控面板

## 3. 分阶段拆解

1. Phase 1（已实现）：后端 Admin API 基础能力
- 仪表盘统计接口
- 用户列表与启停接口
- AI 场景配置管理接口
- AI Provider 管理接口

2. Phase 2（建议 1-2 周）：Vue Vben Admin 接入与页面首版
- 登录页（管理员账号）
- Dashboard 页面（卡片统计 + 趋势图）
- 用户管理页（筛选、分页、启停）
- AI 配置页（scenario/provider 编辑）

3. Phase 3（建议 2-4 周）：安全与审计
- 操作审计日志页面（谁在何时改了什么）
- 关键字段二次确认（API key、停用账号）
- 细粒度 RBAC（菜单权限、按钮权限、数据权限）

4. Phase 4（持续迭代）：运营与可观测
- Celery 任务看板（失败率、重试、耗时）
- WebSocket 在线会话监控
- 文件存储用量、医疗数据规模趋势

## 4. 前后端接口映射（已落地后端）

- `GET /api/admin/v1/dashboard/overview/`
- `GET /api/admin/v1/users/?q=&is_active=&page=&page_size=`
- `POST /api/admin/v1/users/{user_id}/status/`
- `GET /api/admin/v1/ai/scenarios/`
- `PATCH /api/admin/v1/ai/scenarios/{scenario_id}/`
- `GET /api/admin/v1/ai/providers/?kind=`
- `PATCH /api/admin/v1/ai/providers/{provider_id}/`

## 5. Vue Vben Admin 页面建议

1. 仪表盘
- 用户总量、活跃用户、聊天消息总量、文件总量
- 账号注销请求与失败任务提醒

2. 用户管理
- 按用户名/邮箱检索
- 启用/禁用账号
- 后续可扩展：设备列表、登录审计、社交绑定

3. AI 配置管理
- 场景参数（endpoint/model/temperature/max_tokens）
- Provider Key（request_url/is_using/is_active）
- 后续可扩展：配置版本与回滚

## 6. 当前已完成的代码实现

- 新增 `backoffice` Django app
- 新增管理端序列化与视图
- 新增管理端路由 `/api/admin/v1/*`
- 管理接口统一使用 `AdminOnlyPermission`

