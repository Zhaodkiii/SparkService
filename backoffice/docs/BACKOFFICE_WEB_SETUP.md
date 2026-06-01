# Backoffice Web（Vue Vben Admin 风格）启动说明

## 1. 后端准备

1. 迁移数据库

```bash
source .venv/bin/activate
python manage.py migrate
```

2. 初始化 RBAC 权限种子

```bash
python manage.py seed_admin_rbac
```

3. 准备管理员账号

- 使用 Django `createsuperuser` 创建管理员，或将已有用户设为 `is_staff=true`。
- 若使用超级管理员账号，默认可直接通过 `AdminCodePermission`。

## 2. 前端启动

目录：`/Users/hua/Downloads/Reference/SparkService/backoffice-web`

```bash
cd backoffice-web
cp .env.example .env
pnpm install
pnpm dev
```

默认访问：`http://localhost:5173`

## 3. 接口基地址

在 `.env` 里配置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 4. 已接入页面

- 登录页
- 仪表盘
- 用户管理（按钮级权限控制）
- AI 配置（按钮级权限控制）
- RBAC（角色/权限分配）
- 审计日志

## 5. 关键后端接口

- `POST /api/admin/v1/auth/login/`
- `GET /api/admin/v1/auth/profile/`
- `GET /api/admin/v1/dashboard/overview/`
- `GET /api/admin/v1/users/`
- `POST /api/admin/v1/users/{id}/status/`
- `GET /api/admin/v1/ai/scenarios/`
- `PATCH /api/admin/v1/ai/scenarios/{id}/`
- `GET /api/admin/v1/ai/providers/`
- `PATCH /api/admin/v1/ai/providers/{id}/`
- `GET/POST /api/admin/v1/rbac/roles/`
- `GET /api/admin/v1/rbac/permissions/`
- `GET/POST /api/admin/v1/rbac/roles/{id}/permissions/`
- `POST /api/admin/v1/users/{id}/roles/`
- `GET /api/admin/v1/audit/logs/`

