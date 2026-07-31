# 系统日志列表表格风格统一与登录日志收敛需求工单

**工单号**：`BACKOFFICE-AUDIT-000002`

**文档版本**：V1.0

**文档状态**：需求讨论/设计中

**最后更新**：2026-07-30

**适用项目**：SparkService、backoffice-web

**需求来源**：系统日志页面体验复核与附件反馈

**关联工单**：`BACKOFFICE-AUDIT-000001`

> 范围说明：本文只创建新的需求工单，明确系统日志页面的前端表格风格、时间格式、模块收敛和后端模型边界。本文不要求、不允许直接改动项目代码。

---

## 工单索引

| 工单号 | 工单名 | 状态 | 范围 |
| --- | --- | --- | --- |
| `BACKOFFICE-AUDIT-000002` | 系统日志列表表格风格统一与登录日志收敛 | 需求讨论/设计中 | 系统日志单页、统一操作列悬浮风格、统一时间格式、移除登录日志独立视图、不新增 `LoginAudit` 字段 |

---

# 一、背景与问题

## 1.1 当前反馈

系统日志页面需要继续收敛为项目内统一的后台列表体验。附件反馈重点如下：

1. 列表“操作”列需要使用项目中统一的操作列悬浮列表表格风格。
2. 时间需要使用项目内统一标准格式，不能直接展示 `2026-07-30T14:04:27.859000` 这类 ISO 原始值。
3. 不要新增 `accounts.models.LoginAudit` 字段。
4. 审计日志下只保留系统日志，不要再出现“文件日志 / 登录日志”两个 Tab。

## 1.2 当前页面问题表现

系统日志列表字段示例：

```text
时间  级别  logger  状态  耗时  request_id  路径  消息  操作
```

当前容易出现的问题：

1. `时间` 列直接展示后端返回的 ISO 时间，例如 `2026-07-30T14:04:27.859000`。
2. `操作` 列直接使用 `a-space + a-button type="link"`，没有套项目统一的 `TableHoverActions`。
3. 操作列宽度写死，和项目内 `calcActionsColWidth` 规则不一致。
4. 页面存在“文件日志 / 登录日志”Tab，与“只保留系统日志”的新要求冲突。
5. 登录日志如果要求新增数据库字段，会扩大后端模型和迁移范围；本工单明确取消这部分。

# 二、目标与非目标

## 2.1 建设目标

1. 审计日志菜单下保留：

```text
审计日志
  - 操作员日志
  - 系统日志
```

2. 系统日志页面只展示一个系统日志查询页面，不出现：

```text
文件日志
登录日志
```

3. 系统日志表格列固定为：

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

4. `时间` 列必须使用项目统一格式：

```text
YYYY-MM-DD HH:mm:ss
```

5. `操作` 列必须使用项目统一组件：

```text
backoffice-web/src/components/TableHoverActions.vue
backoffice-web/src/utils/tableActionsWidth.ts
```

6. 不新增、不修改 `LoginAudit` 模型字段。

## 2.2 非目标范围

本工单不做：

1. 不新增 `LoginAudit.status_code`。
2. 不新增 `LoginAudit.error_code`。
3. 不新增 `LoginAudit.error_message`。
4. 不新增登录日志独立页面。
5. 不新增“文件日志 / 登录日志”Tab。
6. 不做日志导出。
7. 不改变系统日志原文展示策略。

# 三、关键文件

## 3.1 前端关键文件

| 文件 | 处理要求 | 说明 |
| --- | --- | --- |
| `backoffice-web/src/views/audit/SystemLogView.vue` | 重点调整 | 系统日志页面主体，只保留系统日志查询和列表 |
| `backoffice-web/src/views/AuditView.vue` | 检查 | 作为审计日志入口或容器时，不应显示“文件日志 / 登录日志”Tab |
| `backoffice-web/src/components/TableHoverActions.vue` | 必须复用 | 操作列统一样式 |
| `backoffice-web/src/utils/tableActionsWidth.ts` | 必须复用 | 操作列宽度计算 |
| `backoffice-web/src/utils/datetime.ts` | 必须复用 | `formatDateTime` 时间格式化 |
| `backoffice-web/src/api/modules/audit.ts` | 按需调整类型 | 系统日志接口类型保留；登录日志接口如不再使用应从页面调用中移除 |
| `backoffice-web/src/router/routes.ts` | 检查 | `/audit/system` 指向系统日志页；`/audit` 默认进入操作员日志或系统日志，以最终菜单为准 |
| `backoffice-web/src/layouts/AdminLayout.vue` | 检查 | 审计日志菜单只包含“操作员日志 / 系统日志” |

## 3.2 后端关键文件

| 文件 | 处理要求 | 说明 |
| --- | --- | --- |
| `accounts/models.py` | 禁止新增字段 | 不修改 `LoginAudit` 字段结构 |
| `accounts/migrations/*` | 禁止新增登录审计字段迁移 | 不创建 `loginaudit_error_fields` 类迁移 |
| `backoffice/system_logs/*` | 可保留 | 系统日志文件解析和查询服务可继续作为系统日志能力 |
| `backoffice/system_log_views.py` | 可保留系统日志接口 | 登录日志接口如果仅依赖 `LoginAudit` 新字段，应取消或调整为非本工单范围 |
| `backoffice/urls.py` | 检查 | 系统日志接口保留；登录日志接口按最终页面是否使用决定 |

# 四、前端实现要求

## 4.1 页面结构

系统日志页面目标结构：

```text
系统日志
  筛选区
  告警提示
  日志表格
  分页
  详情抽屉
```

页面不应出现：

```text
文件日志
登录日志
```

日期、排序控件可以保留在筛选区，但不能作为单独 Tab 或裸露标题造成视觉噪声。

## 4.2 筛选区

筛选区保留：

| 控件 | 说明 |
| --- | --- |
| 日期 | 查询 `logs/YYYY-MM-DD/` |
| 日志模块 | 例如 `access`、`accounts_api_io` |
| 状态 | 全部、2xx、3xx、4xx、5xx、200、401、403、500、failed |
| 级别 | DEBUG、INFO、WARNING、ERROR、CRITICAL |
| request_id | 精确筛选 |
| 路径 | 路径筛选 |
| 关键字 | 原文关键字 |
| 排序 | 新到旧、旧到新 |

## 4.3 表格列规范

系统日志表格必须固定这些列：

| 列 | 宽度建议 | 渲染要求 |
| --- | --- | --- |
| 时间 | 180 | 使用 `formatDateTime(record.timestamp)` |
| 级别 | 96 | 使用 `a-tag` 或统一状态展示 |
| logger | 160 | 开启 ellipsis |
| 状态 | 90 | HTTP 状态码；空值展示 `-` |
| 耗时 | 90 | 单位建议显示 `ms`；空值展示 `-` |
| request_id | 260 | 开启 ellipsis |
| 路径 | 260 | 开启 ellipsis |
| 消息 | 自适应 | 开启 ellipsis |
| 操作 | `actionsColWidth` | 固定右侧，使用 `TableHoverActions` |

## 4.4 时间格式要求

系统日志 `timestamp` 可能来自：

```text
2026-07-30T14:04:27.859000
2026-07-30 14:04:27,859
2026-07-30T06:04:27.859Z
```

前端统一使用：

```ts
import { formatDateTime } from '../../utils/datetime';
```

表格列示例：

```vue
<a-table-column title="时间" key="timestamp" :width="180">
  <template #default="{ record }">
    {{ formatDateTime(record.timestamp) }}
  </template>
</a-table-column>
```

最终展示：

```text
2026-07-30 14:04:27
```

不得直接展示：

```text
2026-07-30T14:04:27.859000
```

## 4.5 操作列统一风格

系统日志操作列必须复用：

```ts
import TableHoverActions from '../../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../../utils/tableActionsWidth';
```

示例：

```vue
<a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
  <template #default="{ record }">
    <TableHoverActions>
      <a-button size="small" @click="openDetail(record)">详情</a-button>
      <a-button
        v-if="record.request_id"
        size="small"
        @click="filterByRequestId(record.request_id)"
      >
        同 request_id
      </a-button>
      <a-button
        v-if="record.request_id"
        size="small"
        @click="copyText(record.request_id)"
      >
        复制
      </a-button>
    </TableHoverActions>
  </template>
</a-table-column>
```

宽度示例：

```ts
import { computed } from 'vue';
import { calcActionsColWidth } from '../../utils/tableActionsWidth';

const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: 3,
    min: 220,
    perButton: 64,
  }),
);
```

不建议继续使用：

```vue
<a-space>
  <a-button type="link" size="small">详情</a-button>
  <a-button type="link" size="small">同 request_id</a-button>
  <a-button type="link" size="small">复制 request_id</a-button>
</a-space>
```

原因：与项目现有列表操作列样式不一致，且长按钮文案容易挤压固定列。

## 4.6 操作文案

操作列按钮文案建议：

| 操作 | 文案 | 说明 |
| --- | --- | --- |
| 查看详情 | 详情 | 打开详情抽屉 |
| 同链路筛选 | 同 request_id | 设置筛选条件并刷新 |
| 复制 request_id | 复制 | 复制当前行 request_id |

如果操作列过宽，可把“同 request_id”压缩为“同链路”，但筛选条件仍使用 request_id。

# 五、后端边界要求

## 5.1 不新增 `LoginAudit` 字段

本工单明确不修改：

```text
accounts/models.py
```

不得新增：

```python
status_code = models.IntegerField(...)
error_code = models.IntegerField(...)
error_message = models.CharField(...)
```

不得新增类似迁移：

```text
accounts/migrations/00xx_loginaudit_error_fields.py
```

## 5.2 登录问题只通过系统日志查询

Apple 登录失败、设备凭证异常等问题，使用系统日志查询定位：

```text
date=2026-07-30
module=accounts_api_io
status=401
path=/api/v1/auth/apple/login/
keyword=device_credential_not_registered
```

页面不需要单独构建 `LoginLogPanel`，也不需要新增 `LoginAudit` 查询 Tab。

## 5.3 系统日志接口保持文件查询方向

保留或实现以下系统日志接口即可：

```text
GET /api/admin/v1/audit/system-log-modules/
GET /api/admin/v1/audit/system-logs/
GET /api/admin/v1/audit/system-logs/detail/
```

不要求实现：

```text
GET /api/admin/v1/audit/login-logs/
```

如果该接口已经存在但页面不使用，可作为后续能力保留；本工单验收不依赖该接口。

# 六、页面示例结构

`SystemLogView.vue` 目标结构示例：

```vue
<template>
  <a-space style="margin-bottom: 16px" wrap>
    <a-date-picker v-model:value="fileDate" @change="onDateChange" />
    <a-select v-model:value="query.module" style="width: 180px" @change="loadLogs" />
    <a-select v-model:value="query.status" style="width: 120px" allow-clear placeholder="状态" @change="loadLogs" />
    <a-select v-model:value="query.level" style="width: 120px" allow-clear placeholder="级别" @change="loadLogs" />
    <a-input-search v-model:value="query.request_id" placeholder="request_id" enter-button @search="loadLogs" style="width: 240px" />
    <a-input v-model:value="query.path" placeholder="路径" allow-clear @pressEnter="loadLogs" style="width: 220px" />
    <a-input-search v-model:value="query.keyword" placeholder="关键字" enter-button @search="loadLogs" style="width: 200px" />
    <a-segmented v-model:value="query.order" :options="orderOptions" @change="loadLogs" />
  </a-space>

  <a-table
    :data-source="rows"
    :pagination="false"
    row-key="id"
    :loading="loading"
    :scroll="{ x: 1600 }"
  >
    <a-table-column title="时间" key="timestamp" :width="180">
      <template #default="{ record }">{{ formatDateTime(record.timestamp) }}</template>
    </a-table-column>
    <a-table-column title="级别" data-index="level" :width="96" />
    <a-table-column title="logger" data-index="logger" :width="160" :ellipsis="true" />
    <a-table-column title="状态" key="status_code" :width="90">
      <template #default="{ record }">{{ record.status_code ?? '-' }}</template>
    </a-table-column>
    <a-table-column title="耗时" key="duration_ms" :width="90">
      <template #default="{ record }">{{ record.duration_ms === undefined ? '-' : `${record.duration_ms}ms` }}</template>
    </a-table-column>
    <a-table-column title="request_id" data-index="request_id" :width="260" :ellipsis="true" />
    <a-table-column title="路径" data-index="path" :width="260" :ellipsis="true" />
    <a-table-column title="消息" data-index="message" :ellipsis="true" />
    <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button size="small" @click="openDetail(record)">详情</a-button>
          <a-button v-if="record.request_id" size="small" @click="filterByRequestId(record.request_id)">同 request_id</a-button>
          <a-button v-if="record.request_id" size="small" @click="copyText(record.request_id)">复制</a-button>
        </TableHoverActions>
      </template>
    </a-table-column>
  </a-table>
</template>
```

# 七、验收标准

## 7.1 页面结构

1. `/audit/system` 页面只展示系统日志查询。
2. 页面不出现“文件日志”Tab。
3. 页面不出现“登录日志”Tab。
4. 页面不渲染 `LoginLogPanel`。

## 7.2 表格风格

1. 系统日志表格操作列使用 `TableHoverActions`。
2. 操作列宽度使用 `calcActionsColWidth`。
3. 操作列固定在右侧。
4. 操作按钮使用项目统一小按钮风格，不使用散落的 `a-space + link button`。

## 7.3 时间格式

1. 时间列使用 `formatDateTime`。
2. 页面展示格式为 `YYYY-MM-DD HH:mm:ss`。
3. 不出现 `T`、毫秒或原始 ISO 字符串。

## 7.4 后端模型边界

1. `accounts/models.py` 中 `LoginAudit` 不新增字段。
2. 不新增 `LoginAudit` 字段迁移。
3. 不要求 `/api/admin/v1/audit/login-logs/` 作为本工单验收接口。

## 7.5 系统日志查询

1. 支持按日期查询。
2. 支持选择日志模块。
3. 支持按状态筛选。
4. 支持 `request_id` 筛选。
5. 支持路径和关键字筛选。
6. 支持新到旧、旧到新排序。

# 八、测试建议

## 8.1 前端检查

| 检查项 | 通过标准 |
| --- | --- |
| Tab 收敛 | `SystemLogView.vue` 中无 `a-tabs`、无 `LoginLogPanel` |
| 时间格式 | 列表中 `2026-07-30T14:04:27.859000` 显示为 `2026-07-30 14:04:27` |
| 操作列 | DOM 中操作列按钮位于 `spark-table-hover-actions` 容器内 |
| 操作列宽度 | 使用 `actionsColWidth`，不写死 `width="220"` |
| 右固定 | 操作列 `fixed="right"` |
| 长消息 | `消息`、`路径`、`request_id` 使用 ellipsis，不撑爆表格 |

## 8.2 后端检查

| 检查项 | 通过标准 |
| --- | --- |
| 模型字段 | `LoginAudit` 未新增 `status_code`、`error_code`、`error_message` |
| 迁移文件 | 未新增登录审计字段迁移 |
| 系统日志接口 | `system-logs` 查询仍可返回 `status_code`、`duration_ms`、`request_id` 等解析字段 |

# 九、实施备注

1. 如果当前代码中已经出现 `LoginLogPanel.vue`，本工单要求前端页面不再引用和展示它。
2. 如果当前代码中已经出现登录审计字段迁移，需由实现人员按项目流程单独处理；本工单不要求保留。
3. 系统日志仍可以用 `accounts_api_io` 模块查询 Apple 登录失败，不需要登录日志独立 Tab。
4. 本工单是 UI 和边界收敛工单，优先级高于上一版中“登录日志结构化入库”的扩展设计。

