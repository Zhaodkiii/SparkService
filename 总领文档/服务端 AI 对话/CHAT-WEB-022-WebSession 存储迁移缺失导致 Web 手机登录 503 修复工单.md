# CHAT-WEB-022 WebSession 存储迁移缺失导致 Web 手机登录 503 修复工单

创建日期：2026-08-25  
状态：待实施  
优先级：P0  
问题类型：数据库迁移缺失 / Web 认证阻断  
阶段归属：Web 对话认证与会话维护  
关联工单：`CHAT-WEB-019`、`CHAT-WEB-020`  
关联模块：`accounts`、`AccountWebSession`、Web Phone OTP、Django Migration、MySQL  
本次交付边界：只新增本 Markdown 修复工单，不执行迁移，不修改 Python、TypeScript、Swift、数据库、配置或部署文件。

## 一、模块目标

修复 Chat Web 手机验证码校验成功后无法完成登录的问题：

```text
POST /api/v1/auth/phone/web/otp/verify/
→ HTTP 503
→ code=50373
→ web_session_store_unavailable
```

本工单目标不是重写 Web 手机登录，而是让已经实现的 `AccountWebSession` 会话链路具备真实数据库表，并建立迁移前检查、迁移执行、登录验证和发布门禁。

修复后的目标流程：

```text
请求 Web 手机验证码
  → OTP 创建成功
  → 校验 OTP
  → 解析同一 User
  → 写入 accounts_accountwebsession
  → 签发 session_class=web Token
  → Web 登录成功
  → 不创建或替换任何移动设备会话
```

## 二、WebSession 存储故障模块结构

### 2.1 结构职责表

| 层级 | 当前职责 | 关键代码 |
|---|---|---|
| API 路由 | 暴露 Web Phone OTP request/verify | `accounts/urls.py` |
| API View | 校验 DTO、收集请求上下文、调用登录服务 | `accounts/auth/views.py::WebPhoneOTPRequestView`、`WebPhoneOTPVerifyView` |
| 登录编排 | 复用 OTP/账号解析并注入 Web Token issuer | `accounts/services/web_phone_login_service.py` |
| OTP 事务 | 锁定并消费 OTP、解析账号、调用 Token issuer | `accounts/services/otp_service.py::verify_phone_otp_and_resolve_account` |
| Web 会话领域服务 | 创建 WebSession、签发/刷新/撤销 Web Token | `accounts/services/web_session_service.py` |
| Token | 写入 `web_session_id`、版本和 `session_class=web` | `accounts/auth/web_tokens.py` |
| 数据模型 | 定义独立于移动设备会话的 Web 会话 | `accounts/models.py::AccountWebSession` |
| 数据库迁移 | 创建 WebSession 物理表 | `accounts/migrations/0016_account_web_session.py` |
| 自动化测试 | 验证 Web/Mobile 会话隔离及 Token claim | `accounts/tests_web_phone_login_session.py`、`accounts/tests_web_session_and_apple_login.py` |

### 2.2 具体目录结构

```text
SparkService/
├── manage.py
├── SparkService/
│   └── settings.py
└── accounts/
    ├── urls.py
    ├── models.py
    ├── auth/
    │   ├── serializers.py
    │   ├── views.py
    │   └── web_tokens.py
    ├── services/
    │   ├── otp_service.py
    │   ├── web_phone_login_service.py
    │   └── web_session_service.py
    ├── migrations/
    │   ├── 0015_merge_health_web_identity_scope.py
    │   └── 0016_account_web_session.py
    ├── tests_web_phone_login_session.py
    └── tests_web_session_and_apple_login.py
```

### 2.3 目录职责与依赖方向

```text
accounts/auth/views.py
  → accounts/services/web_phone_login_service.py
  → accounts/services/otp_service.py
  → accounts/services/account_login_resolution_service.py
  → token_issuer callback
  → accounts/services/web_session_service.py
  → accounts/models.py::AccountWebSession
  → MySQL accounts_accountwebsession
```

当前项目是 Django 模块化单体。本功能没有独立 Repository 层，领域服务通过 Django ORM 访问数据库；Migration 是模型与物理表之间的发布契约。

## 三、故障诊断与修复

### 3.1 需求说明

日志显示 OTP 请求阶段成功：

```text
auth.phone_otp.web.request.begin
auth.phone_otp.request.service.whitelist_hit
auth.phone_otp.web.request.success
HTTP 200 / otp_sent
```

OTP 校验阶段失败：

```text
auth.phone_otp.web.verify.begin
auth.phone_otp.verify.service.begin
web.session.store_unavailable
HTTP 503 / code=50373
```

这说明以下能力已经正常：

- Web 专属 URL 和 View 已注册。
- `WEB_PHONE_OTP_LOGIN_ENABLED` 已通过运行门禁。
- Web Service ID 和身份作用域映射可用。
- 手机号规范化、OTP 创建和白名单验证码均正常。
- 请求已进入 Web 专属会话签发路径，没有进入移动 `DeviceSessionService`。

失败发生在 OTP 校验通过后创建 `AccountWebSession` 的数据库写入阶段。

### 3.2 基础要求与业务规则

1. 必须应用仓库中已经存在的 `accounts.0016_account_web_session`。
2. 不新建替代表、不手工创建同名表绕过 Django Migration。
3. 不修改 OTP 验证码、白名单码、尝试次数或有效期。
4. 不允许失败后回退到移动 OTP 登录入口。
5. 不修改 `AccountDeviceSession`、`TrustedDevice` 或移动 Token 刷新规则。
6. 不修改任何 iOS、Android、HarmonyOS 客户端。
7. 迁移必须在承载 Web OTP Verify 流量前完成。
8. 多实例部署必须保证所有 Web 实例连接到已经完成迁移的同一数据库版本。

### 3.3 当前代码证据

`WebPhoneLoginService` 在 OTP 校验成功后调用：

```python
session = WebSessionService.create_session(
    user=user,
    ip_address=ip_address,
    user_agent=user_agent,
    request_id=request_id,
)
```

`WebSessionService.create_session()` 执行：

```python
AccountWebSession.objects.create(...)
```

遇到数据库 `OperationalError` 或 `ProgrammingError` 时，当前实现统一映射为：

```python
APIError(
    "web_session_store_unavailable",
    code=50373,
    status_code=503,
)
```

因此 50373 是服务端有意的 fail-closed 错误，不是浏览器请求 DTO 错误。

### 3.4 已确认根因

本次审计使用项目当前环境连接数据库执行只读检查，结果为：

```text
python3 manage.py showmigrations accounts

[X] 0015_merge_health_web_identity_scope
[ ] 0016_account_web_session
```

迁移计划为：

```text
python3 manage.py migrate accounts --plan

accounts.0016_account_web_session
    Create model AccountWebSession
```

Django 模型对应的目标表名为：

```text
accounts_accountwebsession
```

数据库 introspection 结果：

```text
accounts_accountwebsession exists = false
```

根因结论：应用代码和 Web Phone OTP 路由已经部署，但创建 `AccountWebSession` 所需的 `accounts.0016_account_web_session` 未在当前数据库应用，导致目标表不存在；ORM 插入触发数据库异常，随后被映射为 50373。

### 3.5 修复方案

修复以部署操作为主，原则上不需要修改业务代码：

```text
确认目标环境和数据库
  → 备份/确认数据库恢复点
  → showmigrations accounts
  → migrate accounts --plan
  → 应用 accounts 0016
  → 再次 showmigrations
  → 检查目标表和字段
  → 执行 Web OTP Request/Verify 冒烟
  → 执行 Refresh/Logout/移动共存回归
```

建议由部署系统在 SparkService 应用发布步骤中执行标准 Django Migration：

```bash
python3 manage.py migrate accounts 0016 --noinput
```

也可以由项目统一迁移任务执行：

```bash
python3 manage.py migrate --noinput
```

两种方式只能按项目既有发布规范选择一种，不能由多个 Web 实例启动时并发执行。

### 3.6 验收标准

- `showmigrations accounts` 中 `0016_account_web_session` 为 `[X]`。
- `accounts_accountwebsession` 表真实存在。
- 表字段、索引和外键与迁移文件一致。
- 相同 OTP Verify 请求不再返回 50373。
- 登录成功响应包含 `session_class=web`、Access Token 和 Refresh Token。
- 数据库只新增一条 `AccountWebSession`，不新增移动 Session/TrustedDevice。
- 登录前已在线的移动客户端保持在线。

## 四、迁移发布前检查

### 4.1 需求说明

避免在错误数据库、错误环境或迁移依赖不完整时执行操作。

### 4.2 基础要求与业务规则

发布人员必须核对：

| 检查项 | 成功条件 |
|---|---|
| Git/镜像版本 | 包含 `accounts/migrations/0016_account_web_session.py` |
| Django 设置 | 与实际 Web 进程使用相同 settings module |
| 数据库目标 | DB host/name 与目标环境一致，输出不得泄露密码 |
| 迁移依赖 | `accounts.0015_merge_health_web_identity_scope` 已应用 |
| 迁移计划 | 仅包含预期迁移，不出现意外 destructive operation |
| 数据库权限 | 发布账号拥有 CREATE TABLE/INDEX/FK 所需权限 |
| 恢复点 | 已按生产规范完成备份或时间点恢复确认 |
| 并发控制 | 只有一个受控 Migration Job 执行 |

不得在工单、日志或聊天中输出数据库密码、完整 DSN、Token 或手机号明文。

### 4.3 技术细节与设计代码位置

只读预检命令：

```bash
python3 manage.py showmigrations accounts
python3 manage.py migrate accounts --plan
python3 manage.py check --deploy
```

表结构预期来自：

```text
accounts/migrations/0016_account_web_session.py
accounts/models.py::AccountWebSession
```

### 4.4 验收标准

- 迁移计划经人工确认。
- 目标环境和数据库经双人或自动化部署门禁确认。
- 不存在两个实例同时运行 Migration Job。
- 预检不要求修改客户端或 Web BFF。

## 五、事务一致性与失败恢复

### 5.1 需求说明

确认本次 503 不会造成验证码被永久消费、半个账号或错误会话残留。

### 5.2 基础要求与业务规则

`OTPService.verify_phone_otp_and_resolve_account()` 已由 `@transaction.atomic` 包裹。它在同一事务中：

1. `select_for_update()` 锁定 OTP。
2. 校验验证码。
3. 写入 `otp.used_at`。
4. 解析或创建账号/身份。
5. 调用 Web Token issuer。
6. 创建 `AccountWebSession`。

当第 6 步因数据库异常失败且 APIError 继续抛出事务边界时，整个事务应回滚，包括本次 OTP `used_at` 和本事务中新建的账号/身份数据。

迁移完成后应允许用户使用尚未过期、且事务已回滚为未消费状态的同一 OTP 重试。若 OTP 已过期，则按现有业务规则重新获取，不得手工修改验证码记录。

### 5.3 技术细节与设计代码位置

关键代码：

```text
accounts/services/otp_service.py
  OTPService.verify_phone_otp_and_resolve_account

accounts/services/web_phone_login_service.py
  WebPhoneLoginService.verify_and_issue_tokens

accounts/services/web_session_service.py
  WebSessionService.create_session
```

### 5.4 验收标准

- 模拟 Session insert 异常后，OTP `used_at` 保持为空。
- 失败事务不残留新的 User、SocialIdentity 或 AccountWebSession。
- 重试不产生重复账号或重复身份。
- 同一 OTP 并发校验最多一个请求成功。

## 六、Web 登录会话隔离回归

### 6.1 需求说明

迁移补齐后不能破坏 `CHAT-WEB-019/020` 已定义的 Web/Mobile 会话隔离。

### 6.2 基础要求与业务规则

```text
Web Phone 登录写集合
  ⊆ PhoneOTP + User/SocialIdentity + LoginAudit + AccountWebSession

Web Phone 登录写集合
  ∩ (TrustedDevice + AccountDeviceSession + mobile refresh blacklist)
  = ∅
```

会话矩阵：

| 场景 | 预期结果 |
|---|---|
| iOS 在线后 Web Phone 登录 | iOS 与 Web 同时在线 |
| Android/HarmonyOS 在线后 Web Phone 登录 | Mobile 与 Web 同时在线 |
| Web 在线后移动端登录 | Web 不失效；新 Mobile 按移动单活规则处理 |
| Web A、Web B 登录 | 按现有 Web 多 Session 策略并存 |
| Web Refresh | 只轮换当前 AccountWebSession |
| Web Logout | 只撤销当前 AccountWebSession |
| Mobile Refresh/Logout | 不修改 AccountWebSession |

### 6.3 技术细节与设计代码位置

```text
accounts/services/web_session_service.py
accounts/services/device_session_service.py
accounts/auth/views.py::TokenRefreshView
accounts/auth/authentication.py::SparkJWTAuthentication
accounts/tests_web_phone_login_session.py
accounts/tests_web_session_and_apple_login.py
```

### 6.4 验收标准

- Web Token 只有 `web_session_id`、`web_session_version`、`session_class=web` 会话域字段。
- Web Token 不包含 `device_session_id`、`device_id`。
- Web 登录不导致 `device.session.revoked_on_login` 日志。
- Web 登录不产生 `replaced_by_new_device`。
- 现有移动会话 Access/Refresh Token 继续有效。

## 七、可观测性补强

### 7.1 需求说明

当前日志只有 `web.session.store_unavailable`，应用日志格式没有展示底层 `reason`，无法直接区分“表不存在、数据库断连、权限不足或字段漂移”。

### 7.2 基础要求与业务规则

本次主修复不依赖代码改造。迁移恢复登录后，可将以下内容作为同工单的可观测性补强：

- 记录安全的数据库异常类别，例如 `OperationalError`/`ProgrammingError`。
- 记录稳定的 failure stage：`web_session_create`。
- 记录 migration readiness 布尔值或版本，不记录 SQL、DSN、手机号和 Token。
- 50373 指标按环境、应用版本和实例聚合。
- 启动/发布健康检查发现关键迁移缺失时阻止 Web 登录流量进入。

禁止把原始数据库异常直接返回给客户端。

### 7.3 技术细节与设计代码位置

| 文件 | 建议演进 |
|---|---|
| `accounts/services/web_session_service.py` | 日志增加安全的 `db_error_class`、`failure_stage`；API 仍保持 50373 |
| `accounts/auth/views.py` | LoginAudit 保留 `phone_otp_web_verify` 失败阶段，不记录敏感请求体 |
| 部署健康检查 | 增加关键迁移/目标表 readiness，不在每次登录请求中实时执行 showmigrations |
| 监控规则 | 增加 `web_session_store_unavailable_total` 和 50373 告警 |

### 7.4 验收标准

- 发生 50373 时能通过服务端日志定位环境、实例、版本和安全异常分类。
- API 响应不泄露表名、SQL、数据库地址或堆栈。
- 正常登录不执行额外迁移查询或表扫描。

## 八、整体业务流程

### 8.1 当前失败流程

```text
Browser/BFF
  → POST /auth/phone/web/otp/request/
  → PhoneOTP 创建成功
  → POST /auth/phone/web/otp/verify/
  → OTP 校验通过
  → AccountLoginResolutionService 解析 User
  → WebSessionService.create_session
  → INSERT accounts_accountwebsession
  → 目标表不存在
  → ProgrammingError/OperationalError
  → APIError 50373
  → transaction.atomic 回滚
  → Web 保持未登录
```

### 8.2 修复后流程

```text
受控 Migration Job
  → 应用 accounts.0016
  → 创建 accounts_accountwebsession
  → 记录 django_migrations
  → readiness 通过

Browser/BFF
  → Request OTP 200
  → Verify OTP
  → 创建 AccountWebSession
  → 签发 Web Token
  → Verify 200/login_success
  → BFF 保存 HttpOnly Refresh Cookie
  → Browser 进入 /home
```

## 九、状态模型

### 9.1 部署状态

```text
MIGRATION_MISSING
  → MIGRATION_PLANNED
  → MIGRATION_RUNNING
  → MIGRATION_APPLIED
  → LOGIN_SMOKE_VERIFIED
  → RELEASE_READY
```

失败分支：

```text
MIGRATION_RUNNING
  → MIGRATION_FAILED
  → 停止发布
  → 保留失败证据
  → 根据数据库恢复方案处理
```

### 9.2 登录状态

| 状态 | 含义 | 用户处理 |
|---|---|---|
| OTP_REQUESTED | 验证码已创建 | 输入验证码 |
| VERIFYING | 正在校验并创建 Session | 防止重复点击 |
| STORE_UNAVAILABLE | Session 表不可用 | 保留手机号；提示服务暂不可用 |
| AUTHENTICATED | WebSession 和 Token 已创建 | 进入主页 |
| EXPIRED/REVOKED | Session 到期或撤销 | 重新登录 |

50373 不应由浏览器自动无限重试 Verify，以免造成请求风暴。

## 十、数据与持久化

### 10.1 目标表

`accounts.0016_account_web_session` 创建 `accounts_accountwebsession`，包含：

| 字段 | 用途 |
|---|---|
| `id` | Web Session UUID |
| `user_id` | 关联同一 User |
| `status` | active/revoked/logged_out/expired |
| `session_version` | Token 版本校验 |
| `refresh_jti_hash` | 当前 Refresh JTI 哈希 |
| `user_agent_hash` | 浏览器环境审计哈希 |
| `ip_prefix_hash` | IP 前缀审计哈希 |
| `expires_at` | 会话过期时间 |
| `last_refreshed_at` | 最近刷新时间 |
| `revoked_at/revoked_reason` | 失效审计 |
| `request_id` | 请求链路关联 |
| `created_at/updated_at` | 生命周期时间 |

### 10.2 数据归属

- `AccountWebSession` 归 Web 登录会话域管理。
- `AccountDeviceSession` 和 `TrustedDevice` 归移动会话域管理。
- 不在 WebSession 表保存原始 Refresh Token。
- 不通过手工 SQL 插入 Session 代替登录流程。

## 十一、错误模型

| 场景 | HTTP/code | retryable | 处理 |
|---|---:|---:|---|
| WebSession 表不存在 | 503/50373 | 部署修复前不可重试 | 应用迁移，禁止回退移动登录 |
| 数据库暂时不可用 | 503/50373 | 运维恢复后可重试 | 检查数据库健康 |
| 数据库账号无写权限 | 503/50373 | 配置修复前不可重试 | 修复部署权限 |
| OTP 已使用 | 400/40041 | 否 | 重新获取 OTP |
| OTP 已过期 | 400/40042 | 否 | 重新获取 OTP |
| OTP 错误 | 400/40043 | 剩余次数内可重试 | 保持现有锁定规则 |
| OTP 不可用 | 400/40045 | 否 | 重新获取 OTP |
| Web Session 过期/撤销 | 401/40181-40184 | 按状态 | 重新登录或拒绝重放 |

## 十二、与其他模块的接口边界

### 12.1 本工单负责

- 补齐 `AccountWebSession` 物理表的迁移发布。
- 验证 Web Phone OTP 登录、Refresh 和 Logout。
- 验证 Web/Mobile 会话隔离不变量。
- 建立关键迁移发布门禁和 50373 观测要求。

### 12.2 本工单不负责

- 不修改 Web Phone OTP API 契约。
- 不修改验证码发送供应商或白名单规则。
- 不修改账号合并、Pro 权益或 AI 模型配置。
- 不修改 `/api/v1/ai/config/bootstrap` 或明文 `api_key` 行为。
- 不修改 Web Apple、移动 Apple/JWKS 流程。
- 不修改 iOS、Android、HarmonyOS 登录、刷新或 UI。
- 不修改移动端单活策略。

### 12.3 上下游

| 方向 | 模块 | 边界 |
|---|---|---|
| 上游 | Chat Web BFF/登录页 | 继续使用既有 Web OTP API |
| 编排 | WebPhoneLoginService/OTPService | 保持现有事务和 issuer 注入 |
| 下游 | AccountWebSession/MySQL | 迁移后提供可写物理表 |
| 后续 | TokenRefreshView/SparkJWTAuthentication | 按 Web claim 校验 Session |
| 隔离模块 | DeviceSessionService | 本工单禁止改动 |

## 十三、关键代码对应关系

### 13.1 原则上无需业务代码修改

| 文件 | 本工单处理方向 |
|---|---|
| `accounts/migrations/0016_account_web_session.py` | 直接应用现有迁移，不重新生成同功能迁移 |
| `accounts/models.py` | 只核对模型/表一致性，不修改字段 |
| `accounts/services/web_phone_login_service.py` | 只做登录冒烟与回归，不改变编排 |
| `accounts/services/otp_service.py` | 只验证事务回滚，不修改 OTP 规则 |
| `accounts/services/web_session_service.py` | 主修复无需修改；可选补强脱敏日志 |
| `accounts/auth/views.py` | API 契约保持不变；可选补强审计 |
| `accounts/auth/web_tokens.py` | 不修改 Web Token claim |
| `accounts/services/device_session_service.py` | 禁止改动 |
| `chat-web/` | 主修复原则上无需改动；保持现有 503 提示和输入状态 |

### 13.2 部署与测试改动方向

| 位置 | 改动方向 |
|---|---|
| CI/CD Migration Job | 在应用流量切换前串行执行 Django Migration |
| Deployment readiness | 关键迁移缺失时禁止 Web OTP 登录流量进入 |
| `accounts/tests_web_phone_login_session.py` | 增加 Session insert 异常时 OTP/账号写入回滚测试 |
| `accounts/tests_web_session_and_apple_login.py` | 保留 Web/Mobile 隔离、Refresh/Logout 回归 |
| 运维 Runbook | 记录预检、执行、验证、失败停止和恢复步骤 |

## 十四、测试策略

### 14.1 迁移测试

1. 空测试库从头执行全部 migrations 成功。
2. 已应用 0015 的数据库升级到 0016 成功。
3. 重复运行 `migrate` 为 no-op。
4. 目标表、字段、索引、外键与 Migration State 一致。
5. 应用旧版本在迁移完成后的兼容窗口内不受新增表影响。

### 14.2 API 冒烟测试

1. Request OTP 返回 200/`otp_sent`。
2. Verify OTP 返回 200/`login_success`。
3. 返回 Token 携带 `session_class=web`。
4. 使用 Web Refresh Token 刷新成功。
5. Refresh rotation 后旧 Refresh Token 按现有重放规则失效。
6. Logout 仅撤销当前 WebSession。

### 14.3 事务测试

1. Mock `AccountWebSession.objects.create` 抛出 `OperationalError`。
2. API 返回 50373，不暴露数据库异常。
3. OTP `used_at` 回滚。
4. 本次新建 User/SocialIdentity 回滚。
5. 修复存储后同一未过期 OTP 可以成功重试。
6. 两个并发 Verify 最多创建一个有效登录结果。

### 14.4 会话隔离测试

1. iOS 活跃时 Web Phone 登录，iOS Session 不变。
2. Android/HarmonyOS 活跃时 Web Phone 登录，Mobile Session 不变。
3. Web 登录不创建 TrustedDevice 或 AccountDeviceSession。
4. 移动端后续登录不撤销 WebSession。
5. Web 与移动 Refresh 分别只更新自己的会话表。

## 十五、当前实现、缺口与演进

### 15.1 当前实现

- Web Phone OTP 专属 request/verify API 已存在。
- WebPhoneLoginService 已注入 Web Token issuer。
- AccountWebSession 模型和 0016 Migration 已存在。
- 50373 fail-closed 错误已存在。
- Web/Mobile 独立 Session、Refresh 和 Logout 代码及测试已存在。

### 15.2 当前缺口

- 当前审计连接的数据库尚未应用 `accounts.0016`。
- 目标表 `accounts_accountwebsession` 不存在。
- 当前日志输出没有直接展示安全的底层错误类别。
- 当前发布流程未有效阻止“应用代码已上线、关键迁移未应用”的版本进入流量。

### 15.3 建议演进

1. 把 Django Migration 设为流量切换前的单实例部署任务。
2. 为必须存在的关键迁移建立 release readiness。
3. 为 50373 增加指标和实例/版本维度告警。
4. 增加数据库异常事务回滚测试。

这些建议不改变 Web/Mobile 会话业务规则。

## 十六、发布与回滚

### 16.1 发布顺序

1. 确认目标环境、镜像版本和数据库。
2. 生成并人工核对 migration plan。
3. 确认生产数据库备份或时间点恢复能力。
4. 由单个受控 Migration Job 应用 `accounts.0016`。
5. 核对 Migration State 和目标表结构。
6. 执行 Web Phone Request/Verify 冒烟。
7. 执行 Web Refresh/Logout。
8. 执行移动在线共存回归。
9. 观察 50373、登录成功率和移动 Session 撤销指标。

### 16.2 回滚原则

- 迁移失败时停止发布，不让新应用继续接收 Web OTP Verify 流量。
- 迁移已经成功且产生 WebSession 数据后，不应把 reverse migration 作为常规应用回滚手段，因为反向迁移会删除表和会话数据。
- 应用版本回滚必须选择仍能容忍新增表存在的版本。
- 不通过回退到移动 OTP API 恢复 Web 登录。
- 不删除或手工修改 OTP、User、SocialIdentity、DeviceSession 数据。

## 十七、整体验收标准

- [ ] `accounts.0016_account_web_session` 在目标数据库显示已应用。
- [ ] `accounts_accountwebsession` 表存在且结构正确。
- [ ] Web Phone OTP Request 继续返回 200。
- [ ] Web Phone OTP Verify 不再返回 50373。
- [ ] Verify 成功创建且只创建 AccountWebSession。
- [ ] Web Token claim 正确且不含移动会话字段。
- [ ] Web Refresh 和 Logout 正常。
- [ ] 失败事务会回滚 OTP、账号身份和 Session 写入。
- [ ] Web 登录与移动登录可以同时在线。
- [ ] 移动端之间仍保持既有单活规则。
- [ ] 未修改任何 iOS、Android、HarmonyOS 内容。
- [ ] 未修改移动 Phone OTP、Apple/JWKS、Refresh 安全规则。
- [ ] 未修改 AI bootstrap、Pro、模型或 `api_key` 契约。
- [ ] 发布流程能阻止关键迁移缺失的应用版本进入流量。
- [ ] 日志和响应不泄露手机号、OTP、Token、SQL、DSN 或数据库堆栈。

## 十八、发布门禁

任一条件成立即禁止发布：

1. `accounts.0016` 仍显示未应用。
2. `accounts_accountwebsession` 不存在或字段不完整。
3. Migration Job 目标数据库与 Web 实例数据库不一致。
4. 存在多个应用实例并发执行 migration。
5. Verify 仍返回 50373。
6. 登录成功但未创建 AccountWebSession。
7. Web 登录创建或撤销 AccountDeviceSession/TrustedDevice。
8. Web 登录导致移动端 Token 失效。
9. Web Token 同时包含 Web 与 Device Session claim。
10. 修复方案要求修改移动客户端或回退移动 OTP API。

## 十九、最终结论

本次 Web 手机验证码登录失败不是验证码错误，也不是 Web 请求参数、Token 刷新或移动会话互斥问题。直接根因已经由数据库状态确认：应用代码依赖的 `accounts.0016_account_web_session` 未应用，`accounts_accountwebsession` 物理表不存在。

主修复是通过受控部署流程应用现有 0016 Migration，并完成 Web 登录、Refresh、Logout 和移动会话共存回归。现有 API 对 50373 的 fail-closed 行为应保留；不得通过回退移动登录、放宽 Token 校验或修改移动客户端掩盖数据库迁移缺失。
