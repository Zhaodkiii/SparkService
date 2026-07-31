# 审计日志增加操作员日志与系统日志查询子模块需求工单

**工单号**：`BACKOFFICE-AUDIT-000001`

**文档版本**：V1.0

**文档状态**：需求讨论/设计中

**最后更新**：2026-07-30

**适用项目**：SparkService、backoffice、backoffice-web

**建议模块名**：`backoffice.audit_log` / `backoffice.system_log`

**建议接口前缀**：`/api/admin/v1/audit/*`

> 范围说明：本文只定义需求、设计方案、接口契约、日志解析规则和关键代码示例，不代表代码已实现。本文不修改任何项目代码。

---

## 工单索引

| 工单号 | 工单名 | 状态 | 范围 |
| --- | --- | --- | --- |
| `BACKOFFICE-AUDIT-000001` | 审计日志增加操作员日志与系统日志子模块 | 需求讨论/设计中 | 操作员日志、系统日志文件查询、登录日志查询、日期/模块/状态筛选、日志格式解析 |

---

# 一、背景与问题

## 1.1 当前现状

后台管理系统已有“审计日志”页面，当前页面读取：

```text
GET /api/admin/v1/audit/logs/
```

后端对应 `AdminAuditLogListView`，数据来源为：

```text
backoffice_adminauditlog
```

该页面展示的是后台管理员操作审计，例如：

```text
admin.tasks.manager.start
admin.medical_data.user.members.view
admin.conversation.users.list
```

这类日志用于回答“哪个管理员在后台做了什么操作”。

## 1.2 暴露问题

近期排查 App Apple 登录失败时，运行日志中已能看到：

```text
POST /api/v1/auth/apple/login/ status=401
code=40162
msg=device_credential_not_registered
```

但后台“审计日志”页面无法看到这类登录失败记录，原因是：

1. `/audit` 页面只查 `AdminAuditLog`，不展示 App 登录链路。
2. `LoginAudit` 当前主要在登录成功后写入，部分失败会在业务异常前提前返回，只出现在系统日志文件中。
3. 系统运行日志保存在 `logs/YYYY-MM-DD/*.log`，后台缺少按日期、模块和状态筛选日志文件的能力。
4. 当前日志既可能是 console 文本格式，也可能是 JSON 格式，后台缺少统一解析层。
5. `access_api_io.log` 可能包含请求体、响应体、token、device_secret 等字段，按本工单确认要求，后台展示不做脱敏，便于生产单实例排障。

## 1.3 建设目标

在后台“审计日志”菜单下增加子模块：

```text
审计日志
  - 操作员日志
  - 系统日志
```

其中：

1. **操作员日志**：保留现有 `AdminAuditLog` 列表能力，用于查看后台管理员操作记录。
2. **系统日志**：直接读取 `logs/YYYY-MM-DD/*.log`，支持按日期、日志模块、状态、关键字、request_id、路径筛选；同时承载 App 登录日志查询能力。
3. 根据现有日志格式解析出结构化字段，便于定位登录失败、接口 4xx/5xx、Celery 异常和通知中心调用问题。

# 二、现有日志体系

## 2.1 日志目录

当前 SparkService 日志根目录由 `LOG_ROOT` 控制，默认：

```text
SparkService/logs
```

运行日志按日期目录存放：

```text
logs/YYYY-MM-DD/app.log
logs/YYYY-MM-DD/access.log
logs/YYYY-MM-DD/access_api_io.log
logs/YYYY-MM-DD/celery.log
logs/YYYY-MM-DD/chat_sync.log
logs/YYYY-MM-DD/chat_sync_api_io.log
logs/YYYY-MM-DD/medical_flow.log
logs/YYYY-MM-DD/medical_api_io.log
logs/YYYY-MM-DD/nutrition_api_io.log
logs/YYYY-MM-DD/file_manager.log
logs/YYYY-MM-DD/notification_center.log
```

## 2.2 日志格式

当前 `LOG_FORMAT` 支持：

| 格式 | 说明 | 示例 |
| --- | --- | --- |
| `console` | 文本格式，本地和当前排障常用 | `INFO 2026-07-30 14:04:27,848 accounts.flow [request_id=...] Apple 身份令牌校验成功` |
| `json` | JSON 格式，适合集中采集 | `{"ts":"...","level":"INFO","logger":"accounts.flow","message":"...","request_id":"..."}` |

console 格式模板：

```text
%(levelname)s %(asctime)s %(name)s [request_id=%(request_id)s] %(message)s
```

JSON 格式字段来自 `common.logging.JsonFormatter`，包含：

```text
ts
level
logger
message
request_id
module_name
file
function
line
pid
thread
path
method
status_code
duration_ms
user_id
client_ip
user_agent
response_bytes
error_message
task_id
request_headers
request_body
response_headers
response_body
content_type
```

## 2.3 日志模块映射

生产环境确认为单实例，因此一期系统日志只查询当前 SparkService 实例本地日志文件，不需要跨实例聚合。

系统日志页面的一期模块选项建议固定白名单：

| 模块值 | 展示名 | 文件 | 主要用途 |
| --- | --- | --- | --- |
| `app` | 应用日志 | `app.log` | Django、业务通用日志 |
| `access` | 请求摘要 | `access.log` | HTTP 请求摘要、状态码、耗时 |
| `accounts_api_io` | 账号 API IO | `access_api_io.log` | 账号请求/响应详细日志 |
| `accounts_flow` | 账号流程 | `access.log` / `app.log` | 登录、OTP、设备凭证等流程日志 |
| `celery` | Celery | `celery.log` | 异步任务、worker、beat |
| `chat_sync` | 对话同步 | `chat_sync.log` | 对话同步业务日志 |
| `chat_sync_api_io` | 对话 API IO | `chat_sync_api_io.log` | 对话接口请求/响应 |
| `medical_flow` | 医疗数据流程 | `medical_flow.log` | 医疗数据业务流程 |
| `medical_api_io` | 医疗 API IO | `medical_api_io.log` | 医疗接口请求/响应 |
| `nutrition_api_io` | 营养 API IO | `nutrition_api_io.log` | 营养接口请求/响应 |
| `file_manager` | 文件管理 | `file_manager.log` | 文件上传、OSS、附件处理 |
| `notification_center` | 通知中心 | `notification_center.log` | 短信、通知、回执查询 |

# 三、产品需求

## 3.1 菜单与页面结构

后台菜单调整：

```text
审计日志
  - 操作员日志
  - 系统日志
```

权限建议：

| 权限码 | 名称 | 说明 |
| --- | --- | --- |
| `menu:audit` | 审计日志菜单 | 保留现有菜单入口 |
| `audit:operator:list` | 查看操作员日志 | 查询 `AdminAuditLog` |
| `audit:system:list` | 查看系统日志 | 读取系统日志文件 |
| `audit:system:detail` | 查看系统日志详情 | 查看单条日志完整字段 |
| `audit:system:raw` | 查看日志原文 | 查看完整原始日志行 |
| `audit:system:login` | 查看登录日志 | 查询 App 登录审计与登录相关系统日志 |

一期不提供日志下载，避免日志批量外泄；如后续确需导出，单独评审权限和水印策略。

## 3.2 操作员日志

操作员日志保留现有 `AdminAuditLog` 能力，建议补充筛选：

| 筛选项 | 说明 |
| --- | --- |
| 时间范围 | `created_at` 起止 |
| 管理员 | 按 `user_id` 或用户名 |
| action | 模糊查询 |
| resource_type | 资源类型 |
| status_code | 状态码 |
| request_id | 请求 ID |
| path | 请求路径 |

## 3.3 登录日志能力

登录日志不作为一级菜单子模块，归入“系统日志”子模块中的认证/登录视图。数据来源分两类：

1. 结构化登录审计：`accounts_loginaudit`。
2. 系统运行日志：`logs/YYYY-MM-DD/access.log`、`logs/YYYY-MM-DD/access_api_io.log`、`logs/YYYY-MM-DD/app.log`。

登录日志用于查看 App 用户登录行为。

### 列表字段

| 字段 | 说明 |
| --- | --- |
| 时间 | 登录尝试时间 |
| 用户 | 登录成功时展示 user_id / 用户名；失败未绑定用户时展示 `-` |
| provider | `apple`、`phone_otp`、`email_otp`、`google`、`device` |
| outcome | `success` / `failed` |
| 业务错误码 | 例如 `40162` |
| 错误消息 | 例如 `device_credential_not_registered` |
| bundle_id | 真实客户端 bundle |
| device_id | 完整展示 |
| request_id | 请求链路 ID |
| IP | 完整展示 |
| User-Agent | 客户端版本和系统 |

### 筛选项

| 筛选项 | 说明 |
| --- | --- |
| 日期范围 | 默认今天 |
| provider | 登录方式 |
| outcome | 成功/失败 |
| status_code | HTTP 状态码 |
| error_code | 业务错误码 |
| bundle_id | 客户端包 |
| device_id | 支持精确查询，完整展示 |
| request_id | 精确查询 |
| keyword | 错误消息、User-Agent、raw_claims |

### 失败日志写入要求

后端需补齐失败写入策略。所有认证入口发生业务失败时，均应写入 `LoginAudit(outcome=failed)` 或新建专用扩展模型。

涉及入口：

```text
POST /api/v1/auth/apple/login/
POST /api/v1/auth/device/login/
POST /api/v1/auth/otp/verify/
POST /api/v1/auth/phone/otp/verify/
POST /api/v1/auth/email/otp/verify/
POST /api/v1/auth/google/login/
POST /api/v1/auth/token/refresh/
```

Apple 登录失败示例：

```text
provider=apple
outcome=failed
status_code=401
error_code=40162
error_message=device_credential_not_registered
bundle_id=cn.zhaodk.SupportClient
device_id_hash=<sha256前12位>
request_id=9D37AA5E-8CCF-411E-A5C9-C802740C1826
```

## 3.4 系统日志

系统日志页面直接读取日志文件，解决“数据库审计没有记录，但文件日志里有线索”的排障问题。

### 查询条件

| 条件 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `date` | 日期 | 今天 | 对应 `logs/YYYY-MM-DD/` |
| `module` | 枚举 | `access` | 日志模块，对应文件白名单 |
| `level` | 枚举 | 全部 | `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL` |
| `status` | 枚举/数字 | 全部 | 支持 `2xx`、`3xx`、`4xx`、`5xx` 或具体状态码 |
| `request_id` | 字符串 | 空 | 精确匹配 |
| `path` | 字符串 | 空 | 路径模糊匹配 |
| `keyword` | 字符串 | 空 | 原文/消息模糊匹配 |
| `page` | 数字 | 1 | 分页 |
| `page_size` | 数字 | 50 | 最大 200 |
| `order` | 枚举 | `desc` | `desc` 从新到旧，`asc` 从旧到新 |

### 列表字段

| 字段 | 说明 |
| --- | --- |
| 时间 | 日志时间 |
| 级别 | `INFO` / `WARNING` / `ERROR` |
| logger | 例如 `accounts.api_io` |
| request_id | 链路 ID |
| method | HTTP 方法 |
| path | 请求路径 |
| status_code | HTTP 状态码 |
| duration_ms | 耗时 |
| message | 解析后的消息摘要 |
| raw_preview | 原始日志预览 |

### 详情字段

点击一条日志后展示：

1. 结构化字段表。
2. 原始日志行。
3. request/response headers 摘要。
4. request/response body 原文或完整摘要。
5. 同 request_id 相关日志快捷跳转。

## 3.5 状态筛选规则

系统日志状态筛选需要同时支持 console 和 JSON 格式。

| 输入 | 匹配规则 |
| --- | --- |
| `200` | `status=200`、`status_code=200`、JSON `status_code: 200` |
| `401` | `status=401`、`status_code=401`、JSON `status_code: 401` |
| `4xx` | `400 <= status_code < 500` |
| `5xx` | `500 <= status_code < 600` |
| `failed` | `level in WARNING/ERROR/CRITICAL` 或 message 包含 `failed`、`失败`、`Unauthorized` |

# 四、技术方案

## 4.1 总体架构

```text
backoffice-web
  AuditLayout
    AdminAuditTab
    LoginAuditTab
    SystemLogTab
        |
        v
SparkService backoffice API
  AdminAuditLogListView      -> backoffice_adminauditlog
  AdminLoginLogListView      -> accounts_loginaudit
  AdminSystemLogListView     -> logs/YYYY-MM-DD/*.log
  AdminSystemLogDetailView   -> logs/YYYY-MM-DD/*.log + line_no
        |
        v
SystemLogService
  LogFileRegistry
  ConsoleLogParser
  JsonLogParser
  LogExposurePolicy
  LogPaginator
```

## 4.2 后端新增文件建议

```text
backoffice/
  system_logs.py              # 日志文件发现、读取、解析、筛选
  system_log_serializers.py   # 查询参数和响应序列化
  views.py                    # 或拆分 backoffice/system_log_views.py
  urls.py                     # 新增路由
```

如果后续日志能力继续扩大，建议拆分：

```text
backoffice/system_logs/
  registry.py
  parsers.py
  exposure.py
  service.py
  serializers.py
  views.py
```

## 4.3 接口设计

### 查询登录日志

```text
GET /api/admin/v1/audit/login-logs/
```

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `date_from` | date | 否 | 开始日期 |
| `date_to` | date | 否 | 结束日期 |
| `provider` | string | 否 | 登录方式 |
| `outcome` | string | 否 | `success` / `failed` |
| `status_code` | int | 否 | HTTP 状态码，一期如模型未存则从 raw_claims 取 |
| `error_code` | int | 否 | 业务错误码 |
| `bundle_id` | string | 否 | 客户端 bundle |
| `device_id` | string | 否 | 精确查询 |
| `request_id` | string | 否 | 精确查询 |
| `keyword` | string | 否 | 模糊查询 |
| `page` | int | 否 | 默认 1 |
| `page_size` | int | 否 | 默认 20，最大 100 |

响应示例：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "items": [
      {
        "id": 1001,
        "created_at": "2026-07-30T06:04:27Z",
        "user_id": null,
        "provider": "apple",
        "outcome": "failed",
        "status_code": 401,
        "error_code": 40162,
        "error_message": "device_credential_not_registered",
        "bundle_id": "cn.zhaodk.SupportClient",
        "device_id": "FFC6...3CDE",
        "request_id": "9D37AA5E-8CCF-411E-A5C9-C802740C1826",
        "ip_address": "127.0.0.1",
        "user_agent": "SupportClient/1 CFNetwork/3860.600.12 Darwin/25.5.0"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1
    }
  }
}
```

### 查询系统日志模块

```text
GET /api/admin/v1/audit/system-log-modules/
```

响应示例：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "items": [
      {
        "value": "access",
        "label": "请求摘要",
        "file": "access.log",
        "available_dates": ["2026-07-30", "2026-07-29"]
      },
      {
        "value": "accounts_api_io",
        "label": "账号 API IO",
        "file": "access_api_io.log",
        "available_dates": ["2026-07-30"]
      }
    ]
  }
}
```

### 查询系统日志

```text
GET /api/admin/v1/audit/system-logs/
```

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `date` | date | 是 | 日志日期 |
| `module` | string | 是 | 日志模块白名单值 |
| `level` | string | 否 | 日志级别 |
| `status` | string | 否 | `200`、`401`、`4xx`、`5xx`、`failed` |
| `request_id` | string | 否 | 链路 ID |
| `path` | string | 否 | 路径 |
| `keyword` | string | 否 | 关键字 |
| `page` | int | 否 | 默认 1 |
| `page_size` | int | 否 | 默认 50，最大 200 |
| `order` | string | 否 | `desc` / `asc` |

响应示例：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "items": [
      {
        "id": "2026-07-30:accounts_api_io:1578",
        "date": "2026-07-30",
        "module": "accounts_api_io",
        "file": "access_api_io.log",
        "line_no": 1578,
        "timestamp": "2026-07-30T14:04:27.859+08:00",
        "level": "WARNING",
        "logger": "accounts.api_io",
        "request_id": "9D37AA5E-8CCF-411E-A5C9-C802740C1826",
        "method": "POST",
        "path": "/api/v1/auth/apple/login/",
        "status_code": 401,
        "duration_ms": 1365,
        "message": "HTTP 响应摘要: POST /api/v1/auth/apple/login/ status=401 duration_ms=1365 bytes=116",
        "raw_preview": "WARNING 2026-07-30 14:04:27,859 accounts.api_io [request_id=...] HTTP 响应摘要..."
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 50,
      "total": 1,
      "total_pages": 1
    }
  }
}
```

### 查询系统日志详情

```text
GET /api/admin/v1/audit/system-logs/detail/
```

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `date` | date | 是 | 日志日期 |
| `module` | string | 是 | 日志模块 |
| `line_no` | int | 是 | 行号 |

响应示例：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "date": "2026-07-30",
    "module": "accounts_api_io",
    "file": "access_api_io.log",
    "line_no": 1578,
    "parsed": {
      "level": "WARNING",
      "timestamp": "2026-07-30T14:04:27.859+08:00",
      "logger": "accounts.api_io",
      "request_id": "9D37AA5E-8CCF-411E-A5C9-C802740C1826",
      "method": "POST",
      "path": "/api/v1/auth/apple/login/",
      "status_code": 401,
      "duration_ms": 1365,
      "error_code": 40162,
      "error_message": "device_credential_not_registered"
    },
    "raw": "WARNING 2026-07-30 14:04:27,859 accounts.api_io [request_id=...] HTTP 响应摘要: ...",
    "related_query": {
      "request_id": "9D37AA5E-8CCF-411E-A5C9-C802740C1826"
    }
  }
}
```

## 4.4 日志读取策略

一期直接读取本机日志文件，不引入 Elasticsearch / Loki / OpenSearch。

原因：

1. 当前问题集中在单机或少量部署节点排障。
2. 现有日志已按日期目录和模块文件拆分。
3. 直接读取文件实现成本低，适合快速补齐后台可观测性。

限制：

1. 只支持读取当前 SparkService 实例本地日志。
2. 生产环境已确认为单实例，一期查询当前实例日志即可；多实例集中查询仅作为后续预留。
3. 大文件查询需要行数和扫描上限保护。

建议限制：

| 限制项 | 建议值 |
| --- | --- |
| 单次最大读取文件大小 | 100 MB |
| 单次最大扫描行数 | 200000 |
| 最大 `page_size` | 200 |
| 可查询日期范围 | 最近 `LOG_RETENTION_DAYS` 天 |
| 可查询文件 | 固定白名单，禁止任意路径 |

## 4.5 解析方案

### Console 格式解析

匹配基础结构：

```regex
^(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+
(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+
(?P<logger>[^\s]+)\s+
\[request_id=(?P<request_id>[^\]]+)\]\s+
(?P<message>.*)$
```

再从 `message` 中抽取常用字段：

```regex
\b(?P<method>GET|POST|PUT|PATCH|DELETE|OPTIONS)\s+(?P<path>/[^\s]+)
\bstatus=(?P<status_code>\d{3})\b
\bduration_ms=(?P<duration_ms>\d+)\b
\"code\":\s*(?P<error_code>\d+)
\"msg\":\s*\"(?P<error_message>[^\"]+)\"
```

### JSON 格式解析

优先 `json.loads(line)`，直接读取：

```text
ts
level
logger
message
request_id
path
method
status_code
duration_ms
error_message
request_body
response_body
```

若 JSON 解析失败，降级为 console 文本解析；仍失败时保留：

```text
level=null
timestamp=null
message=<原始行>
parse_status=unparsed
```

## 4.6 原文展示规则

按本工单确认要求，系统日志和登录日志后台展示不做脱敏，超级管理员和具备对应权限的操作员可以查看完整 IP、完整 device_id、完整请求/响应日志内容。

展示规则：

| 类型 | 规则 |
| --- | --- |
| JSON 字段 | 原样展示 |
| Header | 原样展示 |
| request_body | 原样展示 |
| response_body | 原样展示 |
| token / identity_token / authorization_code | 原样展示 |
| device_secret | 原样展示 |
| device_id | 完整展示 |
| IP / 手机号 / 邮箱 | 完整展示 |

安全边界：

1. 仅后台已登录用户可访问。
2. 仅具备 `audit:system:list`、`audit:system:detail`、`audit:system:raw` 权限的操作员可查看系统日志。
3. 一期不提供导出和批量下载。
4. 所有查看系统日志的操作需写入 `AdminAuditLog`，便于追踪谁查看过生产日志。

## 4.7 登录失败审计补齐方案

一期建议分两步实施。

### 第一阶段：系统日志查询先落地

不改变登录业务写入逻辑，仅通过系统日志页面查询：

```text
date=2026-07-30
module=accounts_api_io
status=401
path=/api/v1/auth/apple/login/
```

即可定位 Apple 登录失败。

### 第二阶段：登录失败结构化入库

补齐登录失败审计，建议新增 `LoginAudit` 失败写入工具函数：

```python
def write_login_failure_audit(
    *,
    provider: str,
    bundle_id: str,
    device_id: str = "",
    request_id: str = "",
    ip_address: str = "",
    user_agent: str = "",
    status_code: int | None = None,
    error_code: int | None = None,
    error_message: str = "",
    raw_claims: dict | None = None,
) -> None:
    ...
```

`LoginAudit` 需要增加独立字段：

```text
status_code
error_code
error_message
```

写入字段建议：

```text
provider
outcome=failed
status_code
error_code
error_message
bundle_id
device_id
request_id
ip_address
user_agent
raw_claims.failure_stage
```

`raw_claims` 继续保留扩展诊断上下文，但筛选和列表展示必须优先使用独立字段，不能只依赖 JSON 查询。

# 五、关键代码示例

> 以下为实现参考示例，不是本工单的代码变更。

## 5.1 日志模块注册表示例

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class LogModule:
    value: str
    label: str
    filename: str
    default_logger_prefixes: tuple[str, ...]

LOG_MODULES = {
    "access": LogModule("access", "请求摘要", "access.log", ("accounts.request", "accounts.flow")),
    "accounts_api_io": LogModule("accounts_api_io", "账号 API IO", "access_api_io.log", ("accounts.api_io",)),
    "app": LogModule("app", "应用日志", "app.log", ("django", "accounts")),
    "celery": LogModule("celery", "Celery", "celery.log", ("celery",)),
    "notification_center": LogModule("notification_center", "通知中心", "notification_center.log", ("notification_center",)),
}

def resolve_log_path(log_root: Path, date: str, module: str) -> Path:
    item = LOG_MODULES[module]
    root = log_root.resolve()
    path = (root / date / item.filename).resolve()
    if root not in path.parents:
        raise ValueError("invalid_log_path")
    return path
```

## 5.2 Console 日志解析示例

```python
import re
from datetime import datetime

CONSOLE_RE = re.compile(
    r"^(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<logger>[^\s]+)\s+"
    r"\[request_id=(?P<request_id>[^\]]+)\]\s+"
    r"(?P<message>.*)$"
)

STATUS_RE = re.compile(r"\bstatus=(?P<status_code>\d{3})\b")
DURATION_RE = re.compile(r"\bduration_ms=(?P<duration_ms>\d+)\b")
METHOD_PATH_RE = re.compile(r"\b(?P<method>GET|POST|PUT|PATCH|DELETE|OPTIONS)\s+(?P<path>/[^\s]+)")

def parse_console_line(line: str) -> dict:
    match = CONSOLE_RE.match(line)
    if not match:
        return {"parse_status": "unparsed", "message": line}

    data = match.groupdict()
    message = data["message"]

    status = STATUS_RE.search(message)
    duration = DURATION_RE.search(message)
    method_path = METHOD_PATH_RE.search(message)

    if status:
        data["status_code"] = int(status.group("status_code"))
    if duration:
        data["duration_ms"] = int(duration.group("duration_ms"))
    if method_path:
        data["method"] = method_path.group("method")
        data["path"] = method_path.group("path")

    data["timestamp"] = datetime.strptime(data.pop("ts"), "%Y-%m-%d %H:%M:%S,%f").isoformat()
    data["parse_status"] = "parsed"
    return data
```

## 5.3 JSON 日志解析示例

```python
import json

def parse_log_line(line: str) -> dict:
    stripped = line.strip()
    if not stripped:
        return {"parse_status": "empty"}

    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            pass
        else:
            return {
                "parse_status": "parsed",
                "timestamp": payload.get("ts"),
                "level": payload.get("level"),
                "logger": payload.get("logger"),
                "request_id": payload.get("request_id"),
                "method": payload.get("method"),
                "path": payload.get("path"),
                "status_code": payload.get("status_code"),
                "duration_ms": payload.get("duration_ms"),
                "message": payload.get("message"),
                "raw": payload,
            }

    return parse_console_line(stripped)
```

## 5.4 状态筛选示例

```python
def match_status(row: dict, status: str) -> bool:
    if not status:
        return True

    code = row.get("status_code")
    level = (row.get("level") or "").upper()
    message = row.get("message") or ""

    if status.endswith("xx") and len(status) == 3 and status[0].isdigit():
        if code is None:
            return False
        base = int(status[0]) * 100
        return base <= int(code) < base + 100

    if status.isdigit():
        return int(code or 0) == int(status)

    if status == "failed":
        return level in {"WARNING", "ERROR", "CRITICAL"} or "failed" in message.lower() or "失败" in message

    return True
```

## 5.5 原文展示示例

```python
def expose_log_value(value):
    """
    本工单确认后台系统日志不做脱敏。
    该函数只做 JSON 安全转换，不替换敏感字段。
    """
    if isinstance(value, dict):
        return {str(k): expose_log_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expose_log_value(item) for item in value]
    return value
```

# 六、前端设计方案

## 6.1 路由建议

```text
/audit/admin
/audit/system
```

如果保持原 `/audit`，则 `/audit` 默认重定向到 `/audit/admin`。页面文案统一称为“操作员日志”，避免和 App 登录日志混淆。

## 6.2 页面布局

审计日志页面使用 Tabs 或侧边二级菜单：

```text
[操作员日志] [系统日志]
```

### 系统日志筛选区

控件建议：

| 控件 | 类型 |
| --- | --- |
| 日期 | DatePicker |
| 日志模块 | Select |
| 状态 | Select，选项：全部、2xx、3xx、4xx、5xx、200、400、401、403、500、failed |
| 级别 | Select |
| request_id | Input.Search |
| 路径 | Input |
| 关键字 | Input.Search |
| 排序 | Segmented：新到旧 / 旧到新 |

### 系统日志表格

字段：

```text
时间
级别
logger
状态
耗时
request_id
路径
消息
操作
```

操作：

```text
详情
同 request_id
复制 request_id
```

### 详情抽屉

详情抽屉展示：

```text
基础字段
请求信息
响应信息
错误信息
日志原文
相关日志快捷入口
```

## 6.3 前端类型示例

```ts
export interface SystemLogItem {
  id: string;
  date: string;
  module: string;
  file: string;
  line_no: number;
  timestamp: string | null;
  level: string;
  logger: string;
  request_id: string;
  method?: string;
  path?: string;
  status_code?: number;
  duration_ms?: number;
  message: string;
  raw_preview: string;
}

export interface SystemLogQuery {
  date: string;
  module: string;
  level?: string;
  status?: string;
  request_id?: string;
  path?: string;
  keyword?: string;
  page: number;
  page_size: number;
  order: "asc" | "desc";
}
```

# 七、安全与合规要求

## 7.1 权限控制

1. 系统日志页面必须要求管理员登录。
2. 仅具备 `audit:system:list` 的管理员可查询系统日志。
3. 原始日志详情必须额外要求 `audit:system:detail`。
4. 日志原文按本工单确认要求完整展示，不做脱敏。
5. 不提供日志下载。

## 7.2 路径安全

1. `module` 只能来自后端白名单。
2. `date` 只能是 `YYYY-MM-DD`。
3. 后端使用 `Path.resolve()` 校验最终路径必须位于 `LOG_ROOT` 下。
4. 禁止通过 query 参数传入任意文件名。
5. 文件不存在时返回空列表，不暴露服务器绝对路径。

## 7.3 敏感信息

以下信息按本工单确认要求允许在后台系统日志中明文展示：

```text
identity_token
authorization_code
device_secret
access_token
refresh_token
Authorization
Cookie
password
api_key
```

系统日志页面展示完整日志内容，不做脱敏。实现时必须通过权限控制和操作审计降低误用风险。

# 八、验收标准

## 8.1 操作员日志

1. `/audit/admin` 能展示现有 `AdminAuditLog` 数据。
2. 支持按时间、action、状态码、request_id 查询。
3. 原 `/audit` 默认进入 `/audit/admin`。
4. 页面标题和菜单名称展示为“操作员日志”。

## 8.2 登录日志

1. `/audit/system` 中的登录日志视图或认证日志筛选预设能展示 `LoginAudit` 成功登录数据。
2. Apple 登录失败 `40162` 在补齐失败写入后能按 `outcome=failed` 查询。
3. 支持按 provider、outcome、bundle_id、device_id、request_id、error_code 查询。
4. device_id、IP、邮箱、手机号完整展示。
5. `LoginAudit` 模型具备 `status_code`、`error_code`、`error_message` 独立字段。

## 8.3 系统日志

1. `/audit/system` 默认展示当天 `access.log`。
2. 选择日期 `2026-07-30`、模块 `accounts_api_io`、状态 `401` 后，可以查到 Apple 登录失败请求。
3. 输入 request_id `9D37AA5E-8CCF-411E-A5C9-C802740C1826` 后，可以筛出同链路日志。
4. 支持 console 格式日志解析。
5. 支持 JSON 格式日志解析。
6. 日志详情中 token、authorization_code、device_secret、identity_token 按原文展示。
7. 文件不存在时页面展示空状态，不报 500。
8. 大文件查询触发扫描上限时，接口返回 `truncated=true` 或 `scan_limited=true` 提示。

## 8.4 权限与安全

1. 无 `audit:system:list` 权限的管理员无法访问系统日志。
2. 普通后台用户无法通过路径穿越读取非日志文件。
3. 后端单元测试覆盖路径穿越、权限控制、状态筛选。

# 九、实施拆分建议

## 阶段一：系统日志只读查询

目标：最快解决“登录失败只在文件日志里，后台看不到”的问题。

后端：

1. 新增系统日志模块白名单。
2. 新增日志文件读取服务。
3. 新增 console/json 解析器。
4. 新增原文展示和 JSON 安全转换工具。
5. 新增 `/audit/system-log-modules/`、`/audit/system-logs/`、`/audit/system-logs/detail/`。

前端：

1. 审计日志页面增加“系统日志”子模块。
2. 增加日期、模块、状态、request_id、路径、关键字筛选。
3. 增加详情抽屉。

## 阶段二：登录日志结构化查询

目标：把登录成功/失败统一沉淀为业务审计。

后端：

1. 新增 `/audit/login-logs/`。
2. 梳理 `LoginAudit` 查询和 serializer。
3. 补齐认证失败写入工具函数。
4. 在 Apple、设备、OTP、Google、token refresh 等入口写入失败审计。

前端：

1. 在“系统日志”中增加“登录日志/认证日志”视图或筛选预设。
2. 支持 provider、outcome、error_code、bundle_id、request_id 查询。
3. 从登录审计记录跳转到同 request_id 系统日志。

## 阶段三：集中式日志预留

目标：生产当前是单实例，一期不需要跨机器查询；本阶段仅作为未来扩容为多实例后的架构预留。

预留接口：

```python
class SystemLogBackend:
    def list_modules(self) -> list[dict]:
        ...

    def query(self, query: SystemLogQuery) -> Page:
        ...

    def detail(self, date: str, module: str, line_no: int) -> dict:
        ...
```

一期实现：

```text
LocalFileSystemLogBackend
```

后续可替换为：

```text
LokiSystemLogBackend
OpenSearchSystemLogBackend
AliyunSLSSystemLogBackend
```

# 十、落地实现细节

## 10.1 关键文件清单

### 后端关键文件

| 文件 | 改造类型 | 说明 |
| --- | --- | --- |
| `accounts/models.py` | 修改 | `LoginAudit` 增加 `status_code`、`error_code`、`error_message` 独立字段 |
| `accounts/migrations/00xx_loginaudit_error_fields.py` | 新增 | 登录审计字段迁移 |
| `accounts/services/login_audit_service.py` | 新增 | 登录成功/失败审计统一写入工具 |
| `accounts/services/login_service.py` | 修改 | Apple 登录、token refresh 等失败路径调用审计工具 |
| `accounts/services/device_login_service.py` | 修改 | 设备登录失败路径调用审计工具 |
| `accounts/services/otp_service.py` | 修改 | OTP 登录失败路径调用审计工具 |
| `backoffice/system_logs/registry.py` | 新增 | 系统日志模块白名单和文件路径解析 |
| `backoffice/system_logs/parsers.py` | 新增 | console/json 日志解析 |
| `backoffice/system_logs/exposure.py` | 新增 | 原文展示策略和 JSON 安全转换 |
| `backoffice/system_logs/service.py` | 新增 | 日志文件查询、筛选、分页、详情 |
| `backoffice/system_logs/serializers.py` | 新增 | 查询参数和响应字段 serializer |
| `backoffice/system_log_views.py` | 新增 | 系统日志、登录日志后台 API |
| `backoffice/urls.py` | 修改 | 增加 `/audit/system-*`、`/audit/login-logs/` 路由 |
| `backoffice/rbac.py` | 修改 | 增加操作员日志、系统日志、登录日志权限种子 |
| `backoffice/tests_system_logs.py` | 新增 | 系统日志解析、路径安全、筛选测试 |
| `backoffice/tests_login_audit_admin.py` | 新增 | 登录日志查询与失败写入测试 |

### 前端关键文件

| 文件 | 改造类型 | 说明 |
| --- | --- | --- |
| `backoffice-web/src/views/AuditView.vue` | 修改或拆分 | 改为审计日志容器，内部展示操作员日志/系统日志 |
| `backoffice-web/src/views/audit/OperatorAuditView.vue` | 新增 | 操作员日志表格，承载现有 `AdminAuditLog` |
| `backoffice-web/src/views/audit/SystemLogView.vue` | 新增 | 系统日志查询页 |
| `backoffice-web/src/views/audit/SystemLogDetailDrawer.vue` | 新增 | 系统日志详情抽屉 |
| `backoffice-web/src/views/audit/LoginLogPanel.vue` | 新增 | 系统日志内的登录/认证视图 |
| `backoffice-web/src/api/modules/audit.ts` | 修改 | 增加系统日志、登录日志 API 方法和类型 |
| `backoffice-web/src/router/routes.ts` | 修改 | `/audit` 默认操作员日志；可增加 `/audit/operator`、`/audit/system` |
| `backoffice-web/src/layouts/AdminLayout.vue` | 修改 | 审计日志菜单增加子项 |

## 10.2 后端模型落地

### `LoginAudit` 字段新增

在 `accounts/models.py` 的 `LoginAudit` 增加：

```python
class LoginAudit(models.Model):
    ...
    status_code = models.IntegerField(null=True, blank=True, db_index=True)
    error_code = models.IntegerField(null=True, blank=True, db_index=True)
    error_message = models.CharField(max_length=255, blank=True, default="", db_index=True)
```

迁移示例：

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "00xx_previous"),
    ]

    operations = [
        migrations.AddField(
            model_name="loginaudit",
            name="status_code",
            field=models.IntegerField(null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="loginaudit",
            name="error_code",
            field=models.IntegerField(null=True, blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="loginaudit",
            name="error_message",
            field=models.CharField(max_length=255, blank=True, default="", db_index=True),
        ),
        migrations.AddIndex(
            model_name="loginaudit",
            index=models.Index(
                fields=["provider", "outcome", "created_at"],
                name="login_audit_provider_outcome_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="loginaudit",
            index=models.Index(
                fields=["status_code", "error_code", "created_at"],
                name="login_audit_status_error_created_idx",
            ),
        ),
    ]
```

## 10.3 登录审计写入服务

新增 `accounts/services/login_audit_service.py`：

```python
import logging
from typing import Any

from accounts.models import LoginAudit

logger = logging.getLogger("accounts.flow")


class LoginAuditService:
    @staticmethod
    def write_success(
        *,
        user,
        provider: str,
        bundle_id: str,
        device_id: str = "",
        request_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        raw_claims: dict[str, Any] | None = None,
    ) -> None:
        LoginAuditService._create(
            user=user,
            provider=provider,
            outcome=LoginAudit.LoginOutcome.SUCCESS,
            status_code=200,
            error_code=None,
            error_message="",
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            raw_claims=raw_claims,
        )

    @staticmethod
    def write_failure(
        *,
        provider: str,
        bundle_id: str = "",
        device_id: str = "",
        request_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        status_code: int | None = None,
        error_code: int | None = None,
        error_message: str = "",
        raw_claims: dict[str, Any] | None = None,
        user=None,
    ) -> None:
        LoginAuditService._create(
            user=user,
            provider=provider,
            outcome=LoginAudit.LoginOutcome.FAILED,
            status_code=status_code,
            error_code=error_code,
            error_message=(error_message or "")[:255],
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            raw_claims=raw_claims,
        )

    @staticmethod
    def _create(**kwargs) -> None:
        try:
            LoginAudit.objects.create(**kwargs)
        except Exception as exc:
            logger.warning(
                "login.audit.write_failed request_id=%s provider=%s outcome=%s reason=%s",
                kwargs.get("request_id", ""),
                kwargs.get("provider", ""),
                kwargs.get("outcome", ""),
                str(exc),
            )
```

落地要求：

1. 登录审计写入失败不能影响主登录流程。
2. 失败审计必须在业务异常被返回前写入。
3. `status_code`、`error_code`、`error_message` 必须作为独立字段写入。
4. `raw_claims` 只放扩展上下文，例如 `failure_stage`、`identity_scope`、`apple_aud`。

## 10.4 Apple 登录失败写入示例

在 Apple 登录入口捕获 `APIError` 并写失败审计。示例：

```python
from common.exceptions import APIError
from accounts.models import LoginAudit
from accounts.services.login_audit_service import LoginAuditService


def apple_login_view_or_service(request):
    data = request.data
    request_id = getattr(request, "request_id", "") or ""
    bundle_id = (data.get("bundle_id") or "").strip()
    device_id = (data.get("device_id") or "").strip()
    ip_address = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")) or ""
    user_agent = request.META.get("HTTP_USER_AGENT", "") or ""

    try:
        return LoginService.login_with_apple(...)
    except APIError as exc:
        LoginAuditService.write_failure(
            provider=LoginAudit.LoginProvider.APPLE,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status_code=getattr(exc, "status_code", 400),
            error_code=getattr(exc, "code", None),
            error_message=str(exc),
            raw_claims={
                "failure_stage": "apple_login",
                "apple_user_identifier": data.get("user") or "",
            },
        )
        raise
```

针对 `device_credential_not_registered` 的预期落库：

```text
provider=apple
outcome=failed
status_code=401
error_code=40162
error_message=device_credential_not_registered
bundle_id=cn.zhaodk.SupportClient
device_id=FFC6E375-1913-4883-8F43-4EE1B12B3CDE
request_id=9D37AA5E-8CCF-411E-A5C9-C802740C1826
```

## 10.5 系统日志模块注册

新增 `backoffice/system_logs/registry.py`：

```python
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from common.exceptions import APIError


@dataclass(frozen=True)
class LogModule:
    value: str
    label: str
    filename: str
    default_status_field: str = "status_code"


LOG_MODULES: dict[str, LogModule] = {
    "access": LogModule("access", "请求摘要", "access.log"),
    "accounts_api_io": LogModule("accounts_api_io", "账号 API IO", "access_api_io.log"),
    "app": LogModule("app", "应用日志", "app.log"),
    "celery": LogModule("celery", "Celery", "celery.log"),
    "chat_sync": LogModule("chat_sync", "对话同步", "chat_sync.log"),
    "chat_sync_api_io": LogModule("chat_sync_api_io", "对话 API IO", "chat_sync_api_io.log"),
    "medical_flow": LogModule("medical_flow", "医疗数据流程", "medical_flow.log"),
    "medical_api_io": LogModule("medical_api_io", "医疗 API IO", "medical_api_io.log"),
    "nutrition_api_io": LogModule("nutrition_api_io", "营养 API IO", "nutrition_api_io.log"),
    "file_manager": LogModule("file_manager", "文件管理", "file_manager.log"),
    "notification_center": LogModule("notification_center", "通知中心", "notification_center.log"),
}


def resolve_log_file(*, date: str, module: str) -> Path:
    if module not in LOG_MODULES:
        raise APIError("invalid_log_module", code=40071, status_code=400)

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise APIError("invalid_log_date", code=40072, status_code=400)

    root = Path(settings.LOG_ROOT).resolve()
    path = (root / date / LOG_MODULES[module].filename).resolve()
    if root != path and root not in path.parents:
        raise APIError("invalid_log_path", code=40073, status_code=400)
    return path
```

## 10.6 系统日志解析器

新增 `backoffice/system_logs/parsers.py`：

```python
import json
import re
from datetime import datetime


CONSOLE_RE = re.compile(
    r"^(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<logger>[^\s]+)\s+"
    r"\[request_id=(?P<request_id>[^\]]+)\]\s+"
    r"(?P<message>.*)$"
)
STATUS_RE = re.compile(r"\bstatus(?:_code)?=(?P<status_code>\d{3})\b")
DURATION_RE = re.compile(r"\bduration_ms=(?P<duration_ms>\d+)\b")
METHOD_PATH_RE = re.compile(r"\b(?P<method>GET|POST|PUT|PATCH|DELETE|OPTIONS)\s+(?P<path>/[^\s]+)")
ERROR_CODE_RE = re.compile(r'"code"\s*:\s*(?P<error_code>\d+)')
ERROR_MSG_RE = re.compile(r'"msg"\s*:\s*"(?P<error_message>[^"]+)"')


def parse_log_line(line: str) -> dict:
    raw = line.rstrip("\n")
    if not raw:
        return {"parse_status": "empty", "raw": raw}

    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            pass
        else:
            return {
                "parse_status": "parsed",
                "timestamp": payload.get("ts"),
                "level": payload.get("level"),
                "logger": payload.get("logger"),
                "request_id": payload.get("request_id"),
                "method": payload.get("method"),
                "path": payload.get("path"),
                "status_code": payload.get("status_code"),
                "duration_ms": payload.get("duration_ms"),
                "message": payload.get("message") or "",
                "raw": payload,
            }

    match = CONSOLE_RE.match(raw)
    if not match:
        return {"parse_status": "unparsed", "message": raw, "raw": raw}

    row = match.groupdict()
    message = row["message"]
    row["timestamp"] = datetime.strptime(row.pop("ts"), "%Y-%m-%d %H:%M:%S,%f").isoformat()
    row["parse_status"] = "parsed"
    row["raw"] = raw

    for regex, key, caster in (
        (STATUS_RE, "status_code", int),
        (DURATION_RE, "duration_ms", int),
        (ERROR_CODE_RE, "error_code", int),
        (ERROR_MSG_RE, "error_message", str),
    ):
        found = regex.search(message)
        if found:
            row[key] = caster(found.group(key))

    method_path = METHOD_PATH_RE.search(message)
    if method_path:
        row["method"] = method_path.group("method")
        row["path"] = method_path.group("path")

    return row
```

## 10.7 系统日志查询服务

新增 `backoffice/system_logs/service.py`：

```python
from dataclasses import dataclass

from common.exceptions import APIError
from .parsers import parse_log_line
from .registry import LOG_MODULES, resolve_log_file


MAX_SCAN_LINES = 200_000
MAX_PAGE_SIZE = 200


@dataclass
class SystemLogQuery:
    date: str
    module: str
    level: str = ""
    status: str = ""
    request_id: str = ""
    path: str = ""
    keyword: str = ""
    page: int = 1
    page_size: int = 50
    order: str = "desc"


def match_status(row: dict, status: str) -> bool:
    if not status:
        return True
    code = row.get("status_code")
    message = row.get("message") or ""
    level = (row.get("level") or "").upper()

    if status.endswith("xx") and len(status) == 3 and status[0].isdigit():
        if code is None:
            return False
        start = int(status[0]) * 100
        return start <= int(code) < start + 100
    if status.isdigit():
        return int(code or 0) == int(status)
    if status == "failed":
        return level in {"WARNING", "ERROR", "CRITICAL"} or "failed" in message.lower() or "失败" in message
    return True


class SystemLogService:
    @staticmethod
    def list_modules() -> list[dict]:
        return [
            {"value": item.value, "label": item.label, "file": item.filename}
            for item in LOG_MODULES.values()
        ]

    @staticmethod
    def query(query: SystemLogQuery) -> dict:
        path = resolve_log_file(date=query.date, module=query.module)
        page_size = min(max(query.page_size, 1), MAX_PAGE_SIZE)
        page = max(query.page, 1)

        if not path.exists():
            return {"items": [], "pagination": {"page": page, "page_size": page_size, "total": 0, "total_pages": 0}}

        rows = []
        scan_limited = False
        with path.open("r", encoding="utf-8", errors="replace") as fp:
            for line_no, line in enumerate(fp, start=1):
                if line_no > MAX_SCAN_LINES:
                    scan_limited = True
                    break
                row = parse_log_line(line)
                row.update({"line_no": line_no, "date": query.date, "module": query.module, "file": path.name})
                if not SystemLogService._match(row, query):
                    continue
                rows.append(row)

        if query.order == "desc":
            rows.reverse()

        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": rows[start:end],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
            },
            "scan_limited": scan_limited,
        }

    @staticmethod
    def detail(*, date: str, module: str, line_no: int) -> dict:
        path = resolve_log_file(date=date, module=module)
        if not path.exists():
            raise APIError("log_file_not_found", code=40471, status_code=404)
        with path.open("r", encoding="utf-8", errors="replace") as fp:
            for current, line in enumerate(fp, start=1):
                if current == line_no:
                    row = parse_log_line(line)
                    row.update({"line_no": line_no, "date": date, "module": module, "file": path.name})
                    return row
        raise APIError("log_line_not_found", code=40472, status_code=404)

    @staticmethod
    def _match(row: dict, query: SystemLogQuery) -> bool:
        if query.level and (row.get("level") or "").upper() != query.level.upper():
            return False
        if query.request_id and row.get("request_id") != query.request_id:
            return False
        if query.path and query.path not in (row.get("path") or "") and query.path not in (row.get("message") or ""):
            return False
        if query.keyword and query.keyword.lower() not in str(row.get("raw", "")).lower():
            return False
        return match_status(row, query.status)
```

## 10.8 后台 API 视图

建议新增 `backoffice/system_log_views.py`，避免继续膨胀 `backoffice/views.py`。

```python
from rest_framework.views import APIView

from backoffice.audit import write_audit_log
from backoffice.permissions import AdminOnlyPermission
from common.responses import success_response
from .system_logs.service import SystemLogQuery, SystemLogService


class AdminSystemLogModuleListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        payload = {"items": SystemLogService.list_modules()}
        write_audit_log(request, action="admin.audit.system.modules.view", resource_type="system_log")
        return success_response(payload, msg="success", code=0)


class AdminSystemLogListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        q = SystemLogQuery(
            date=request.query_params.get("date", ""),
            module=request.query_params.get("module", "access"),
            level=request.query_params.get("level", ""),
            status=request.query_params.get("status", ""),
            request_id=request.query_params.get("request_id", ""),
            path=request.query_params.get("path", ""),
            keyword=request.query_params.get("keyword", ""),
            page=int(request.query_params.get("page", "1")),
            page_size=int(request.query_params.get("page_size", "50")),
            order=request.query_params.get("order", "desc"),
        )
        payload = SystemLogService.query(q)
        write_audit_log(
            request,
            action="admin.audit.system.logs.view",
            resource_type="system_log",
            response_payload={"date": q.date, "module": q.module, "total": payload["pagination"]["total"]},
        )
        return success_response(payload, msg="success", code=0)


class AdminSystemLogDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        payload = SystemLogService.detail(
            date=request.query_params.get("date", ""),
            module=request.query_params.get("module", "access"),
            line_no=int(request.query_params.get("line_no", "0")),
        )
        write_audit_log(
            request,
            action="admin.audit.system.log.detail",
            resource_type="system_log",
            resource_id=f"{payload.get('date')}:{payload.get('module')}:{payload.get('line_no')}",
        )
        return success_response(payload, msg="success", code=0)
```

路由接入 `backoffice/urls.py`：

```python
from backoffice.system_log_views import (
    AdminLoginAuditListView,
    AdminSystemLogDetailView,
    AdminSystemLogListView,
    AdminSystemLogModuleListView,
)

urlpatterns = [
    ...
    path("audit/logs/", AdminAuditLogListView.as_view(), name="admin-audit-log-list"),
    path("audit/login-logs/", AdminLoginAuditListView.as_view(), name="admin-login-audit-list"),
    path("audit/system-log-modules/", AdminSystemLogModuleListView.as_view(), name="admin-system-log-module-list"),
    path("audit/system-logs/", AdminSystemLogListView.as_view(), name="admin-system-log-list"),
    path("audit/system-logs/detail/", AdminSystemLogDetailView.as_view(), name="admin-system-log-detail"),
]
```

## 10.9 登录日志后台查询视图

`AdminLoginAuditListView` 示例：

```python
from django.core.paginator import Paginator
from django.db.models import Q
from rest_framework.views import APIView

from accounts.models import LoginAudit
from backoffice.serializers import AdminLoginAuditSerializer
from common.responses import success_response


class AdminLoginAuditListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = LoginAudit.objects.select_related("user").all().order_by("-created_at", "-id")

        provider = (request.query_params.get("provider") or "").strip()
        outcome = (request.query_params.get("outcome") or "").strip()
        request_id = (request.query_params.get("request_id") or "").strip()
        bundle_id = (request.query_params.get("bundle_id") or "").strip()
        device_id = (request.query_params.get("device_id") or "").strip()
        error_code = (request.query_params.get("error_code") or "").strip()
        status_code = (request.query_params.get("status_code") or "").strip()
        keyword = (request.query_params.get("keyword") or "").strip()

        if provider:
            queryset = queryset.filter(provider=provider)
        if outcome:
            queryset = queryset.filter(outcome=outcome)
        if request_id:
            queryset = queryset.filter(request_id=request_id)
        if bundle_id:
            queryset = queryset.filter(bundle_id=bundle_id)
        if device_id:
            queryset = queryset.filter(device_id=device_id)
        if error_code.isdigit():
            queryset = queryset.filter(error_code=int(error_code))
        if status_code.isdigit():
            queryset = queryset.filter(status_code=int(status_code))
        if keyword:
            queryset = queryset.filter(
                Q(error_message__icontains=keyword)
                | Q(user_agent__icontains=keyword)
                | Q(raw_claims__icontains=keyword)
            )

        page = int(request.query_params.get("page", "1"))
        page_size = min(int(request.query_params.get("page_size", "20")), 100)
        page_obj = Paginator(queryset, page_size).get_page(page)

        payload = {
            "items": AdminLoginAuditSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page_obj.number,
                "page_size": page_size,
                "total": page_obj.paginator.count,
                "total_pages": page_obj.paginator.num_pages,
            },
        }
        write_audit_log(request, action="admin.audit.login.logs.view", resource_type="login_audit")
        return success_response(payload, msg="success", code=0)
```

`backoffice/serializers.py` 增加：

```python
class AdminLoginAuditSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = LoginAudit
        fields = (
            "id",
            "user",
            "user_name",
            "provider",
            "outcome",
            "status_code",
            "error_code",
            "error_message",
            "ip_address",
            "user_agent",
            "bundle_id",
            "device_id",
            "raw_claims",
            "request_id",
            "created_at",
        )
```

## 10.10 RBAC 权限种子

`backoffice/rbac.py` 当前已有：

```python
("menu:audit", "审计日志", "menu", "/audit", "")
```

建议扩展：

```python
("menu:audit", "审计日志", "menu", "/audit", ""),
("menu:audit:operator", "操作员日志", "menu", "/audit/admin", "menu:audit"),
("menu:audit:system", "系统日志", "menu", "/audit/system", "menu:audit"),
("audit:operator:list", "查看操作员日志", "api", "/api/admin/v1/audit/logs/", ""),
("audit:system:list", "查看系统日志", "api", "/api/admin/v1/audit/system-logs/", ""),
("audit:system:detail", "查看系统日志详情", "api", "/api/admin/v1/audit/system-logs/detail/", ""),
("audit:system:raw", "查看系统日志原文", "api", "/api/admin/v1/audit/system-logs/detail/", ""),
("audit:system:login", "查看登录日志", "api", "/api/admin/v1/audit/login-logs/", ""),
```

如果当前 `AdminOnlyPermission` 尚未细分到权限码，一期可以沿用超级管理员/管理员权限，二期再接入精确权限校验。

## 10.11 前端 API 类型

修改 `backoffice-web/src/api/modules/audit.ts`：

```ts
export interface LoginAuditItem {
  id: number;
  user: number | null;
  user_name: string;
  provider: string;
  outcome: 'success' | 'failed';
  status_code: number | null;
  error_code: number | null;
  error_message: string;
  ip_address: string;
  user_agent: string;
  bundle_id: string;
  device_id: string;
  raw_claims: Record<string, unknown> | null;
  request_id: string;
  created_at: string;
}

export interface SystemLogModule {
  value: string;
  label: string;
  file: string;
}

export interface SystemLogItem {
  date: string;
  module: string;
  file: string;
  line_no: number;
  timestamp: string | null;
  level: string;
  logger: string;
  request_id: string;
  method?: string;
  path?: string;
  status_code?: number;
  duration_ms?: number;
  error_code?: number;
  error_message?: string;
  message: string;
  raw: unknown;
}

export function fetchLoginAuditLogs(params: Record<string, unknown>) {
  return http.get<unknown, { items: LoginAuditItem[]; pagination: Pagination }>('/api/admin/v1/audit/login-logs/', { params });
}

export function fetchSystemLogModules() {
  return http.get<unknown, { items: SystemLogModule[] }>('/api/admin/v1/audit/system-log-modules/');
}

export function fetchSystemLogs(params: Record<string, unknown>) {
  return http.get<unknown, { items: SystemLogItem[]; pagination: Pagination; scan_limited?: boolean }>('/api/admin/v1/audit/system-logs/', { params });
}

export function fetchSystemLogDetail(params: { date: string; module: string; line_no: number }) {
  return http.get<unknown, SystemLogItem>('/api/admin/v1/audit/system-logs/detail/', { params });
}
```

## 10.12 前端路由和菜单

`backoffice-web/src/router/routes.ts` 建议：

```ts
{ path: '/audit', redirect: '/audit/admin' },
{ path: '/audit/admin', name: 'OperatorAudit', component: () => import('../views/audit/OperatorAuditView.vue'), meta: { title: '操作员日志' } },
{ path: '/audit/system', name: 'SystemLog', component: () => import('../views/audit/SystemLogView.vue'), meta: { title: '系统日志' } },
```

`backoffice-web/src/layouts/AdminLayout.vue` 菜单建议：

```ts
{
  code: 'menu:audit',
  name: '审计日志',
  path: '/audit',
  children: [
    { code: 'menu:audit:operator', name: '操作员日志', path: '/audit/admin', children: [] },
    { code: 'menu:audit:system', name: '系统日志', path: '/audit/system', children: [] },
  ],
}
```

## 10.13 系统日志页面状态

`SystemLogView.vue` 必须具备以下 UI 状态：

| 状态 | 页面行为 |
| --- | --- |
| 初始态 | 默认 date=今天、module=access、status=全部 |
| 加载态 | 表格 loading，不清空筛选条件 |
| 空态 | 文件不存在或无匹配日志时展示空状态 |
| 超限态 | `scan_limited=true` 时展示“日志文件较大，本次只扫描前 200000 行” |
| 错误态 | 400/403/500 展示错误提示和 request_id |
| 详情态 | 抽屉展示完整解析字段和原始日志 |

登录日志视图建议作为 `SystemLogView.vue` 内部 tab：

```text
系统日志
  [文件日志] [登录日志]
```

这样菜单仍保持：

```text
审计日志
  - 操作员日志
  - 系统日志
```

## 10.14 实施顺序

建议按下面顺序实施，便于每一步都可单独验收：

1. 后端增加 `LoginAudit` 三个字段和迁移。
2. 新增 `LoginAuditService.write_failure`，先接 Apple 登录失败。
3. 新增 `/api/admin/v1/audit/login-logs/`，前端暂不接。
4. 新增系统日志 registry/parser/service，完成后端测试。
5. 新增 `/api/admin/v1/audit/system-log-modules/`、`system-logs/`、`detail/`。
6. 前端拆分 `/audit/admin` 和 `/audit/system`。
7. 在 `SystemLogView` 接入文件日志查询。
8. 在 `SystemLogView` 增加登录日志 tab。
9. 补齐设备登录、OTP、Google、token refresh 的失败审计。
10. 全量回归权限、路径安全、大文件限制和原文展示。

## 10.15 最小可交付版本

若需要先快速上线排障，最小版本只包含：

1. `/audit` 重定向 `/audit/admin`。
2. 菜单增加“操作员日志 / 系统日志”。
3. 系统日志支持 `date + module + status + request_id + keyword` 查询。
4. 支持 `access.log`、`access_api_io.log`、`app.log` 三个文件。
5. 支持 console 格式解析。
6. 原文展示，不做脱敏。

登录审计独立字段和失败入库可以作为第二个提交，但必须在同一需求工单验收范围内完成。

# 十一、测试建议

## 11.1 后端单元测试

| 测试项 | 说明 |
| --- | --- |
| console 解析 | 能解析 level、timestamp、logger、request_id、message |
| status 解析 | 能从 `status=401` 提取状态码 |
| duration 解析 | 能从 `duration_ms=1365` 提取耗时 |
| JSON 解析 | 能解析 JsonFormatter 输出 |
| 状态筛选 | `401`、`4xx`、`5xx`、`failed` 均正确 |
| 路径安全 | `../settings.py` 无法读取 |
| 文件不存在 | 返回空结果 |
| 原文展示 | token、device_secret、identity_token 均按原文返回 |
| 分页 | page/page_size 正确 |
| 大文件限制 | 超限时返回提示 |

## 11.2 前端验收测试

| 测试项 | 说明 |
| --- | --- |
| 默认加载 | 进入系统日志默认加载今天 access |
| 日期切换 | 切换日期后重新请求 |
| 模块切换 | 选择 accounts_api_io 后读取 access_api_io.log |
| 状态筛选 | 选择 401 后只展示 401 |
| 关键字筛选 | 输入 apple/login 可命中 |
| request_id 筛选 | 精确命中同链路 |
| 详情抽屉 | 展示结构化字段与日志原文 |
| 空状态 | 文件不存在时展示空态 |
| 无权限 | 展示 403 或无权限页 |

# 十二、风险与注意事项

1. `access_api_io.log` 可能包含原始请求体；本工单确认不做脱敏，必须严格依赖后台权限和查看审计。
2. 大日志文件不能一次性完整读入内存，应流式读取或限制扫描行数。
3. 系统日志查询是排障工具，不应替代长期审计数据库。
4. 生产环境确认为单实例，一期无需标注多实例节点信息；如后续扩容为多实例，应切换集中式日志查询。
5. 如果生产启用 JSON 日志，console 解析规则仍要保留，用于本地和历史日志。
6. 登录失败入库要避免二次抛错影响主流程，审计失败应降级写系统日志。
7. 日志保留天数受 `LOG_RETENTION_DAYS` 和实际清理策略影响，前端日期可选范围应以后端返回为准。

# 十三、开放问题

1. 生产环境是否为单实例？已确认：生产单实例，一期只查当前实例。
2. 是否允许查看完整 IP、完整 device_id？已确认：允许完整展示，不做脱敏。
3. `LoginAudit` 是否增加独立字段？已确认：增加 `status_code`、`error_code`、`error_message`。
4. 系统日志是否需要支持导出？待确认；一期默认不做导出。
5. `/audit` 默认页如何处理？已确认：`/audit` 默认进入“操作员日志”，审计日志下只保留“操作员日志”和“系统日志”两个子模块。
