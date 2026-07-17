# 用户管理页面字段排序、Pro 权益与设备版本号优化需求工单

创建日期：2026-07-16  
关联项目：`SparkService`、`backoffice-web`  
关联模块：后台用户管理、用户详情、设备信息、Pro 试用权益  
优先级：P1  
需求类型：后台管理体验优化 / 用户排障能力增强 / 权益运营操作

## 1. 背景

当前后台用户管理页面已经具备用户列表、用户详情、启用/禁用用户、登录设备信息和登录会话流水展示能力。

现有用户列表示例：

| ID | 显示名称 | 账号标识 | 邮箱 | 状态 | 最近使用时间 | 操作 |
|---:|---|---|---|---|---|---|
| 784 | 孔维玲 | apple_000023.9a2d495f6 | d6kt5c8j5s@privaterelay.appleid.com | 启用 | 2026-06-26 08:06:49 |  |
| 783 | 我是泥碟 | apple_001435.5714a1cf9 | apple_001435.5714a@privaterelay.appleid.com | 启用 | 2026-06-25 22:10:14 |  |
| 782 | 陶程钰 | apple_000456.3ebd42711 | 6bpwz4ckbd@privaterelay.appleid.com | 启用 | 2026-06-25 21:10:28 |  |
| 781 | deleted_user_18_1782383661 | deleted_user_18_1782383661 | deleted_18_1782383661@anonymized.local | 禁用 |  |  |

现有用户详情示例：

| 字段 | 值 |
|---|---|
| 用户 ID | 784 |
| 显示名称 | 孔维玲 |
| 账号标识 | apple_000023.9a2d495f6 |
| 邮箱 | d6kt5c8j5s@privaterelay.appleid.com |
| 状态 | 启用 |
| 是否 Staff | 否 |
| 是否 Superuser | 否 |
| 注册时间 | 2026-06-26 08:06:49 |
| 最近登录 | - |

现有登录设备信息已经展示设备 ID、bundle、平台、系统版本、设备型号、通知权限、国家地区、语言、最近上报等字段，但缺少应用版本号和构建号，不利于排查“某个用户是否仍在旧版本 App 上”的问题。

## 2. 目标

1. 用户列表支持按 `ID` 排序。
2. 用户列表支持按 `最近使用时间` 排序。
3. 用户列表新增 `注册时间` 字段，并支持排序。
4. 用户列表新增 `是否 Pro` 字段。
5. 用户详情新增 `是否 Pro`、Pro 状态、开始时间、到期时间、发放来源等信息。
6. 用户详情支持对用户发放 Pro 权益和回收 Pro 权益。
7. 用户详情的登录设备信息增加应用版本号展示。
8. 保持现有用户启用/禁用、详情弹窗、设备信息、会话流水能力不受影响。

## 3. 非目标

1. 本工单不重做用户管理页面整体布局。
2. 本工单不新增用户编辑能力。
3. 本工单不修改账号登录、设备上报、版本检查的客户端协议。
4. 本工单不改变 Pro 试用业务规则本身，只在后台用户管理中增加查询和操作入口。
5. 本工单不迁移历史设备数据；历史未上报应用版本号的设备展示为空或 `-`。

## 4. 当前实现依据

### 4.1 前端现状

用户管理页面：

```text
backoffice-web/src/views/UsersView.vue
```

当前列表字段：

- `id`
- `display_name`
- `username`
- `email`
- `is_active`
- `last_used_at`

当前详情弹窗已经展示：

- 用户基础信息
- `trusted_devices`
- `device_sessions`

当前前端类型：

```text
backoffice-web/src/types/index.ts
backoffice-web/src/api/modules/users.ts
```

### 4.2 服务端现状

用户列表接口：

```http
GET /api/admin/v1/users/
```

服务端位置：

```text
backoffice/views.py
AdminUserListView
```

当前查询默认排序：

```python
.order_by("-date_joined", "-id")
```

当前 `last_used_at` 由以下候选值计算：

- `TrustedDevice.last_seen`
- `AccountDeviceSession.last_refreshed_at`
- `User.last_login`

用户详情接口：

```http
GET /api/admin/v1/users/{user_id}/detail/
```

服务端位置：

```text
backoffice/views.py
AdminUserDetailView
```

当前返回：

- `user`
- `trusted_devices`
- `device_sessions`

Pro 试用权益模型和后台试用期操作已经存在：

```text
ai_config.models.TrialApplication
backoffice.views.AdminAITrialActionView
```

当前 AI 试用期页面已有 `approve/reject/recycle/grant` 等动作，但用户管理详情页还没有按用户聚合 Pro 状态和 Pro 操作入口。

## 5. 用户列表需求

### 5.1 列表字段

用户管理列表调整为：

| 字段 | 数据来源 | 是否排序 | 展示要求 |
|---|---|---|---|
| ID | `user.id` | 是 | 数字，默认可点击排序 |
| 显示名称 | `display_name` | 否 | 空值显示 `-` |
| 账号标识 | `username` | 否 | 长文本允许省略 |
| 邮箱 | `email` | 否 | 空值显示 `-` |
| 状态 | `is_active` | 可选 | 启用绿色，禁用红色 |
| 是否 Pro | `is_pro` | 可选 | Pro 显示绿色标签，非 Pro 显示灰色 |
| 注册时间 | `date_joined` | 是 | 使用统一时间格式 |
| 最近使用时间 | `last_used_at` | 是 | 空值显示 `-` |
| 操作 | 现有操作 | 不涉及 | 保持现有能力 |

建议列顺序：

```text
ID / 显示名称 / 账号标识 / 邮箱 / 状态 / 是否 Pro / 注册时间 / 最近使用时间 / 操作
```

### 5.2 排序交互

需要支持排序字段：

| 前端列 | sort_by | 允许 order |
|---|---|---|
| ID | `id` | `asc` / `desc` |
| 注册时间 | `date_joined` | `asc` / `desc` |
| 最近使用时间 | `last_used_at` | `asc` / `desc` |

默认排序建议：

```text
sort_by=date_joined
order=desc
```

前端点击表头时调用：

```http
GET /api/admin/v1/users/?page=1&page_size=20&sort_by=id&order=desc
GET /api/admin/v1/users/?page=1&page_size=20&sort_by=last_used_at&order=desc
GET /api/admin/v1/users/?page=1&page_size=20&sort_by=date_joined&order=desc
```

切换排序时：

1. 重置到第一页。
2. 保留当前搜索关键词和状态筛选。
3. 后端分页基于排序后的结果。

### 5.3 公共排序能力要求

本次排序能力不能只在 `UsersView.vue` 中临时实现。后台列表页面后续会持续增加可排序字段，需要抽象成公共能力，避免每个页面重复解析 Ant Design Vue sorter、重复维护 `sort_by/order` 参数和默认排序逻辑。

统一目标：

1. 前端提供公共排序 composable 或工具函数。
2. 后端提供统一排序白名单 helper。
3. 页面只声明“哪些字段可排序”和“默认排序”，不重复写排序解析细节。
4. 所有后台列表的排序 UI、参数名、空值处理和重置分页行为保持一致。
5. 用户管理页作为首个接入页面，后续设备管理、通知日志、版本日志、AI 试用期等页面可快速复用。

#### 5.3.1 前端公共排序契约

建议新增：

```text
backoffice-web/src/composables/useTableSort.ts
```

职责：

1. 保存当前 `sort_by/order`。
2. 将 Ant Design Vue 的 `sorter.order` 转换为后端参数：
   - `ascend -> asc`
   - `descend -> desc`
   - 空排序 -> 默认排序
3. 切换排序时自动把分页重置到第一页。
4. 生成表格列需要的 `sorter` 和 `sortOrder` 状态。
5. 提供统一 query 参数，供 API 请求直接展开。

建议接口：

```ts
type SortOrder = 'asc' | 'desc';

interface SortFieldConfig {
  key: string;
  apiField: string;
  defaultOrder?: SortOrder;
}

const {
  sortQuery,
  getColumnSortOrder,
  handleTableChange,
  resetSort,
} = useTableSort({
  defaultSortBy: 'date_joined',
  defaultOrder: 'desc',
  fields: {
    id: { key: 'id', apiField: 'id' },
    date_joined: { key: 'date_joined', apiField: 'date_joined' },
    last_used_at: { key: 'last_used_at', apiField: 'last_used_at' },
  },
  onSortChange: () => {
    query.page = 1;
    load();
  },
});
```

页面使用示例：

```vue
<a-table
  :data-source="rows"
  :pagination="false"
  row-key="id"
  :loading="loading"
  :scroll="{ x: 1300 }"
  @change="handleTableChange"
>
  <a-table-column
    title="ID"
    data-index="id"
    :sorter="true"
    :sort-order="getColumnSortOrder('id')"
  />
</a-table>
```

请求参数统一：

```ts
await fetchUsers({
  ...query,
  ...sortQuery.value,
});
```

#### 5.3.2 前端统一风格要求

所有后台表格排序统一使用 Ant Design Vue 表头排序样式，不额外自绘排序图标。

统一规则：

| 项 | 规则 |
|---|---|
| 参数名 | `sort_by` / `order` |
| 升序值 | `asc` |
| 降序值 | `desc` |
| 默认排序 | 页面声明，不在组件里写死 |
| 取消排序 | 回到页面默认排序 |
| 切换排序 | 自动回到第一页 |
| 多列排序 | 暂不支持，一次只允许一个字段 |

#### 5.3.3 后端公共排序契约

建议新增后端 helper：

```text
backoffice/sorting.py
```

职责：

1. 读取 `sort_by/order`。
2. 校验字段是否在白名单内。
3. 返回稳定的 `order_by` 列表。
4. 自动追加兜底排序字段，避免分页时同值乱序。
5. 统一处理非法排序参数。

建议接口：

```python
def resolve_admin_sort(
    request,
    *,
    allowed: dict[str, dict[str, list[str]]],
    default: tuple[str, str],
) -> list[str]:
    ...
```

用户管理接入示例：

```python
order_by = resolve_admin_sort(
    request,
    allowed={
        "id": {
            "asc": ["id"],
            "desc": ["-id"],
        },
        "date_joined": {
            "asc": ["date_joined", "id"],
            "desc": ["-date_joined", "-id"],
        },
        "last_used_at": {
            "asc": ["last_used_sort", "id"],
            "desc": ["-last_used_sort", "-id"],
        },
    },
    default=("date_joined", "desc"),
)
queryset = queryset.order_by(*order_by)
```

非法参数处理：

| 参数 | 处理 |
|---|---|
| `sort_by` 不在白名单 | 回退默认排序 |
| `order` 不是 `asc/desc` | 回退默认排序 |
| 字段需要注解但注解不存在 | 后端测试覆盖，开发期失败，不在运行期静默错误 |

#### 5.3.4 公共能力验收

1. 用户管理不直接手写 sorter 到 `sort_by/order` 的转换逻辑。
2. 用户管理通过公共 `useTableSort` 或等价工具接入排序。
3. 后端不在 `AdminUserListView` 中散落 if/else 排序判断，使用公共排序 helper 或等价白名单封装。
4. 新页面新增排序字段时，只需要配置字段映射和后端白名单。
5. 排序样式和交互与 Ant Design Vue 表格保持一致。

### 5.4 最近使用时间排序定义

`last_used_at` 是计算字段，排序必须在服务端完成，不能只在当前页前端排序。

建议服务端注解：

```python
queryset = User.objects.annotate(
    _max_device_seen=Max("trusted_devices__last_seen"),
    _max_session_refresh=Max("device_sessions__last_refreshed_at"),
    last_used_sort=Greatest(
        Coalesce("_max_device_seen", MIN_DT),
        Coalesce("_max_session_refresh", MIN_DT),
        Coalesce("last_login", MIN_DT),
    ),
)
```

如果数据库或 ORM 对 `Greatest/Coalesce` 的时区处理复杂，短期可使用 `Case/When` 或子查询实现，但排序结果必须与序列化输出的 `last_used_at` 一致。

空值排序规则：

| 排序 | 空值位置 |
|---|---|
| `desc` | 最后 |
| `asc` | 最后 |

即无最近使用时间的用户不要排到最前面。

### 5.5 是否 Pro 字段定义

列表新增字段：

```json
{
  "is_pro": true,
  "pro_status": "active",
  "pro_expires_at": "2026-08-15T12:00:00Z"
}
```

字段含义：

| 字段 | 类型 | 说明 |
|---|---|---|
| `is_pro` | boolean | 当前是否为有效 Pro 用户 |
| `pro_status` | string | `none/pending/active/expired/rejected` 等试用状态 |
| `pro_expires_at` | datetime/null | Pro 到期时间 |

服务端计算建议：

1. 批量预取或子查询 `TrialApplication`，避免列表 N+1。
2. 使用 `TrialService.ensure_status_fresh` 或等价逻辑确保过期状态刷新。
3. `is_pro=true` 的标准应与客户端登录返回 `is_pro`、Pro 配置接口判断保持一致。

## 6. 用户详情需求

### 6.1 用户基础信息新增 Pro 信息

用户详情基础信息新增：

| 字段 | 展示 |
|---|---|
| 是否 Pro | 是 / 否 |
| Pro 状态 | `active/pending/expired/rejected/none` 对应中文 |
| Pro 来源 | 自动发放 / 系统发放 / 申请通过 / - |
| Pro 开始时间 | `started_at` |
| Pro 到期时间 | `expires_at` |
| Pro 剩余时间 | 按天或小时展示，可选 |

建议详情响应新增：

```json
{
  "pro": {
    "is_pro": true,
    "status": "active",
    "grant_source": "manual",
    "started_at": "2026-07-16T09:08:51Z",
    "expires_at": "2026-08-15T09:08:51Z",
    "remaining_seconds": 2592000,
    "trial_id": 81,
    "latest_request_id": 149
  }
}
```

### 6.2 用户详情 Pro 操作

用户详情支持：

1. 发放 Pro 权益。
2. 回收 Pro 权益。

按钮展示规则：

| 当前状态 | 展示按钮 |
|---|---|
| 非 Pro / 无试用记录 / 已过期 / 已拒绝 | 发放 Pro |
| Pro 生效中 | 回收 Pro |
| pending | 可展示发放 Pro，也可提示先处理申请，产品可二选一 |

发放 Pro 弹窗字段：

| 字段 | 说明 |
|---|---|
| 发放天数 | 默认使用系统试用天数，可选填 |
| 到期时间 | 可选，和发放天数二选一 |
| 备注 | 可选，写入试用记录 note |

回收 Pro 弹窗字段：

| 字段 | 说明 |
|---|---|
| 备注 | 必填或选填，由产品确认；建议必填 |

操作完成后：

1. 刷新用户详情。
2. 刷新当前列表行的 `is_pro/pro_status/pro_expires_at`。
3. 写入后台审计日志。
4. 如会员通知策略启用，按通知中心会员工单发送或不发送对应通知。

### 6.3 推荐服务端接口

为了用户管理页能直接按用户操作，建议新增按 user_id 的 Pro 管理接口，避免前端必须先查 trial_id。

发放：

```http
POST /api/admin/v1/users/{user_id}/pro/grant/
```

请求：

```json
{
  "grant_days": 30,
  "expires_at": null,
  "note": "客服补偿"
}
```

回收：

```http
POST /api/admin/v1/users/{user_id}/pro/recycle/
```

请求：

```json
{
  "note": "误发回收"
}
```

响应统一返回最新用户详情或 Pro 摘要：

```json
{
  "user_id": 784,
  "pro": {
    "is_pro": false,
    "status": "expired",
    "grant_source": "manual",
    "started_at": "2026-07-16T09:08:51Z",
    "expires_at": "2026-07-16T09:30:00Z",
    "trial_id": 81
  }
}
```

权限建议：

| 动作 | 权限码 |
|---|---|
| 查看 Pro 信息 | 复用用户详情查看权限 |
| 发放 Pro | `button:user:pro:grant` 或复用 `button:ai:trial:grant` |
| 回收 Pro | `button:user:pro:recycle` 或复用 `button:ai:trial:recycle` |

建议新增用户管理语义权限码，避免用户详情页依赖 AI 试用期页面按钮权限。

### 6.4 和现有 AI 试用接口的关系

现有 AI 试用期页面已经有：

```text
AdminAITrialActionView
action=grant/recycle
```

用户管理详情页可以复用同一套领域逻辑，但不建议前端直接依赖 `trial_id` 接口，因为：

1. 用户可能还没有 `TrialApplication` 记录。
2. 用户详情页的操作对象是 user，不是 trial。
3. 前端为了发放 Pro 先创建或查找 trial 会增加耦合。

推荐做法：

1. 服务端抽取 `TrialService.admin_grant_user_trial(...)`。
2. 服务端抽取 `TrialService.admin_recycle_user_trial(...)`。
3. `AdminAITrialActionView` 和用户管理 Pro 接口复用同一服务方法。

## 7. 登录设备信息新增应用版本号

### 7.1 字段需求

用户详情中的登录设备信息表新增：

| 字段 | 数据来源 | 展示 |
|---|---|---|
| 应用版本 | `TrustedDevice.app_version` | 例如 `1.4.2` |
| 构建号 | `TrustedDevice.build_version` | 例如 `102` |
| 包标识 | `TrustedDevice.bundle_identifier` | 可选，必要时展示 |

建议表格列顺序：

```text
ID / device_id / bundle_id / 应用版本 / 构建号 / 平台 / 系统版本 / 设备型号 / 设备名称 / 通知权限 / push_token / 国家/地区 / 语言 / 模拟器 / 是否失效 / 首次登记 / 最近上报 / request_id
```

如果空间不足，`包标识` 可先不作为主列，放入详情 tooltip 或后续展开字段。

### 7.2 服务端序列化

`AdminUserTrustedDeviceSerializer` 增加：

```python
"app_version",
"build_version",
"bundle_identifier",
```

前端类型 `AdminUserTrustedDevice` 同步增加：

```ts
app_version: string;
build_version: string;
bundle_identifier: string;
```

### 7.3 空值处理

历史设备可能没有应用版本号：

| 值 | 展示 |
|---|---|
| 空字符串 | `-` |
| null | `-` |
| 有值 | 原样展示 |

## 8. 前端实现设计

### 8.1 公共排序 composable

新增：

```text
backoffice-web/src/composables/useTableSort.ts
```

该 composable 是后台表格排序的统一入口，用户管理页只是首个接入页面。后续页面增加排序能力时，不允许复制用户管理页里的排序逻辑。

公共能力至少包含：

1. 当前排序状态。
2. Ant Design Vue sorter 到 `sort_by/order` 的转换。
3. 默认排序回退。
4. `sortOrder` 回显。
5. 排序变化时触发 `onSortChange`。

### 8.2 `UsersView.vue`

改造点：

1. 用户列表增加 `是否 Pro` 列。
2. 用户列表增加 `注册时间` 列。
3. `ID`、`注册时间`、`最近使用时间` 表头支持排序。
4. 通过公共 `useTableSort` 接入排序。
5. 请求参数展开公共 `sortQuery`。
6. 用户详情基础信息增加 Pro 信息。
7. 用户详情增加发放 Pro / 回收 Pro 操作按钮。
8. 登录设备信息增加应用版本和构建号列。

建议 query：

```ts
const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  is_active: '',
});
```

排序配置：

```ts
const { sortQuery, getColumnSortOrder, handleTableChange } = useTableSort({
  defaultSortBy: 'date_joined',
  defaultOrder: 'desc',
  fields: {
    id: { key: 'id', apiField: 'id' },
    date_joined: { key: 'date_joined', apiField: 'date_joined' },
    last_used_at: { key: 'last_used_at', apiField: 'last_used_at' },
  },
  onSortChange: () => {
    query.page = 1;
    load();
  },
});
```

请求：

```ts
const data = await fetchUsers({
  ...query,
  ...sortQuery.value,
});
```

### 8.3 API 模块

`backoffice-web/src/api/modules/users.ts`：

```ts
export function fetchUsers(params: {
  page: number;
  page_size: number;
  q?: string;
  is_active?: string;
  sort_by?: string;
  order?: 'asc' | 'desc';
}) { ... }

export function grantUserPro(userId: number, payload: { grant_days?: number; expires_at?: string | null; note?: string }) {
  return http.post(`/api/admin/v1/users/${userId}/pro/grant/`, payload);
}

export function recycleUserPro(userId: number, payload: { note?: string }) {
  return http.post(`/api/admin/v1/users/${userId}/pro/recycle/`, payload);
}
```

### 8.4 类型定义

`AdminUser` 增加：

```ts
is_pro: boolean;
pro_status: string;
pro_expires_at: string | null;
```

`AdminUserDetail` 增加：

```ts
pro: {
  is_pro: boolean;
  status: string;
  grant_source: string;
  started_at: string | null;
  expires_at: string | null;
  remaining_seconds: number;
  trial_id: number | null;
  latest_request_id: number | null;
};
```

`AdminUserTrustedDevice` 增加：

```ts
app_version: string;
build_version: string;
bundle_identifier: string;
```

## 9. 服务端实现设计

### 9.1 公共排序 helper

新增：

```text
backoffice/sorting.py
```

该 helper 是后台列表服务端排序的统一入口，用户管理页作为首个接入页面。后续页面不得在各自 View 中重复写分散的排序 if/else。

建议提供：

```python
def resolve_admin_sort(
    request,
    *,
    allowed: dict[str, dict[str, list[str]]],
    default: tuple[str, str],
) -> list[str]:
    ...
```

要求：

1. 只允许白名单字段排序。
2. 统一识别 `sort_by/order`。
3. 统一回退默认排序。
4. 每个排序配置必须包含稳定兜底字段，例如 `id/-id`。
5. 不把用户输入直接拼接进 `order_by`。

### 9.2 用户列表接口

`AdminUserListView` 支持：

```text
sort_by=id|date_joined|last_used_at
order=asc|desc
```

非法排序字段回退到：

```text
date_joined desc, id desc
```

排序建议：

| sort_by | order_by |
|---|---|
| `id asc` | `id` |
| `id desc` | `-id` |
| `date_joined asc` | `date_joined`, `id` |
| `date_joined desc` | `-date_joined`, `-id` |
| `last_used_at asc` | `last_used_sort`, `id`，空值最后 |
| `last_used_at desc` | `-last_used_sort`, `-id`，空值最后 |

注意：需要避免 `TrustedDevice` 和 `AccountDeviceSession` join 导致重复用户。当前使用聚合注解时，应确认 SQL 产生正确的 `GROUP BY`。

### 9.3 Pro 状态批量计算

列表页建议通过子查询或预取计算：

```python
trial_qs = TrialApplication.objects.filter(user_id=OuterRef("pk")).order_by("-updated_at", "-id")
queryset = queryset.annotate(
    pro_status=Subquery(trial_qs.values("status")[:1]),
    pro_expires_at=Subquery(trial_qs.values("expires_at")[:1]),
)
```

`is_pro` 判断不能只看 `status=active`，还要确认 `expires_at > now` 或 `TrialApplication.is_active_trial()` 等价逻辑。

如果担心 ORM 注解复杂，可以在分页后批量查询当前页用户的 TrialApplication，再由 serializer context 注入，避免 N+1。

### 9.4 用户详情接口

`AdminUserDetailView` 返回增加：

```json
{
  "user": {
    "id": 784,
    "is_pro": true,
    "pro_status": "active",
    "pro_expires_at": "2026-08-15T09:08:51Z"
  },
  "pro": {
    "is_pro": true,
    "status": "active",
    "grant_source": "manual",
    "started_at": "2026-07-16T09:08:51Z",
    "expires_at": "2026-08-15T09:08:51Z",
    "remaining_seconds": 2592000,
    "trial_id": 81,
    "latest_request_id": 149
  }
}
```

### 9.5 Pro 操作接口

新增视图：

```text
AdminUserProGrantView
AdminUserProRecycleView
```

或一个动作视图：

```text
AdminUserProActionView(user_id, action)
```

路由建议：

```python
path("users/<int:user_id>/pro/grant/", AdminUserProGrantView.as_view())
path("users/<int:user_id>/pro/recycle/", AdminUserProRecycleView.as_view())
```

操作规则：

1. 发放时若不存在 `TrialApplication`，创建一条。
2. 发放时若已存在，更新为 `ACTIVE`。
3. 回收时若不存在 Pro 记录，返回 400 或幂等成功；建议返回 400 `pro_not_found`。
4. 回收时将状态置为 `EXPIRED`，`expires_at=now`。
5. 操作写审计日志。
6. 操作后返回最新 Pro 摘要。

## 10. 权限与审计

### 10.1 权限

建议新增权限：

| 权限码 | 用途 |
|---|---|
| `button:user:pro:grant` | 用户详情发放 Pro |
| `button:user:pro:recycle` | 用户详情回收 Pro |

前端按钮展示：

1. 当前用户拥有权限才显示对应按钮。
2. Superuser 默认拥有全部权限。
3. 无权限时不展示按钮，不只是在点击时报错。

### 10.2 审计日志

发放 Pro：

```text
action=admin.user.pro.grant
resource_type=user
resource_id={user_id}
```

回收 Pro：

```text
action=admin.user.pro.recycle
resource_type=user
resource_id={user_id}
```

审计 payload 建议包含：

- `trial_id`
- `previous_status`
- `new_status`
- `expires_at`
- `note`
- `operator_user_id`

## 11. 测试建议

### 11.1 服务端测试

用户列表：

1. `sort_by=id&order=asc` 返回 ID 升序。
2. `sort_by=id&order=desc` 返回 ID 降序。
3. `sort_by=date_joined&order=desc` 返回注册时间倒序。
4. `sort_by=last_used_at&order=desc` 返回最近使用时间倒序。
5. 无最近使用时间的用户排在最后。
6. 列表返回 `is_pro/pro_status/pro_expires_at`。
7. 搜索、状态筛选和排序同时存在时结果正确。
8. 非法 `sort_by/order` 通过公共排序 helper 回退默认排序。
9. 排序结果自动追加稳定兜底字段，分页不重复、不漏数据。

用户详情：

1. 返回 Pro 摘要。
2. 返回设备 `app_version/build_version/bundle_identifier`。
3. 无 Pro 记录时 `is_pro=false/status=none`。
4. Pro 已过期时 `is_pro=false/status=expired`。

Pro 操作：

1. 无 Pro 用户可发放 Pro。
2. 已有过期 Pro 用户可重新发放 Pro。
3. Pro 用户可回收 Pro。
4. 无权限用户不能发放或回收。
5. 操作写审计日志。

### 11.2 前端测试

1. `useTableSort` 能把 `ascend/descend` 转成 `asc/desc`。
2. `useTableSort` 能在取消排序时回到页面默认排序。
3. `useTableSort` 能正确回显当前排序列。
4. 点击 ID 表头触发服务端排序请求。
5. 点击注册时间表头触发服务端排序请求。
6. 点击最近使用时间表头触发服务端排序请求。
7. 用户管理页面不手写重复 sorter 解析逻辑。
8. 列表展示是否 Pro 标签。
9. 详情弹窗展示 Pro 信息。
10. 详情弹窗可发放 Pro，成功后刷新详情和列表。
11. 详情弹窗可回收 Pro，成功后刷新详情和列表。
12. 设备表展示应用版本和构建号。
13. 历史空版本号展示 `-`。

## 12. 验收标准

1. 用户列表出现 `是否 Pro` 和 `注册时间` 列。
2. ID、注册时间、最近使用时间支持服务端排序。
3. 前端排序接入公共 `useTableSort` 或等价公共工具，不在 `UsersView.vue` 中重复造轮子。
4. 后端排序接入公共 `resolve_admin_sort` 或等价白名单 helper，不在 `AdminUserListView` 中散落排序 if/else。
5. 排序参数统一为 `sort_by/order`，页面风格和交互与 Ant Design Vue 表格排序保持一致。
6. 排序后翻页结果稳定，不出现重复或漏用户。
7. 用户列表 `是否 Pro` 与详情页 Pro 状态一致。
8. 用户详情展示是否 Pro、Pro 状态、来源、开始时间、到期时间。
9. 有权限管理员可以在用户详情发放 Pro。
10. 有权限管理员可以在用户详情回收 Pro。
11. 发放/回收后列表和详情立即刷新为最新状态。
12. 登录设备信息展示应用版本号和构建号。
13. 无应用版本号的历史设备不报错，展示 `-`。
14. 所有新增 Pro 操作写入审计日志。
15. 现有用户启用/禁用、详情、设备、会话流水能力不回归。
16. 前端类型检查和构建通过。
17. 后端测试通过。

## 13. 涉及文件

前端：

- `backoffice-web/src/views/UsersView.vue`
- `backoffice-web/src/api/modules/users.ts`
- `backoffice-web/src/types/index.ts`
- `backoffice-web/src/composables/useTableSort.ts`

后端：

- `backoffice/views.py`
- `backoffice/serializers.py`
- `backoffice/urls.py`
- `backoffice/rbac.py`
- `backoffice/tests.py`
- `backoffice/sorting.py`
- `ai_config/services.py`
- `ai_config/models.py`

## 14. 备注

用户管理页是客服和运营排查用户问题的主入口。本次优化后，管理员可以在一个弹窗里看到用户身份、活跃时间、注册时间、Pro 权益、登录设备、应用版本号和登录会话，减少在用户管理、设备管理、AI 试用期多个页面之间来回切换。
