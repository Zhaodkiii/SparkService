# 用户管理日期范围筛选 TypeScript 构建失败修复工单

## 1. 工单背景

2026-07-16 执行 SparkService 发布前端构建时，`backoffice-web` 在 TypeScript 校验阶段失败，导致发布流程被阻断。

本工单只处理用户管理页面日期范围筛选导致的构建失败问题，不包含部署脚本、健康检查、回滚等部署链路逻辑。

## 2. 问题现象

执行后台前端构建：

```bash
cd /Users/hua/Documents/project/Reference/SparkService/backoffice-web
pnpm build
```

构建阶段报错：

```text
src/views/UsersView.vue:506:41 - error TS2339: Property 'format' does not exist on type 'string | Dayjs'.
  Property 'format' does not exist on type 'string'.

506   query.date_joined_before = values[1]?.format('YYYY-MM-DD HH:mm:ss') || '';
                                            ~~~~~~

src/views/UsersView.vue:516:39 - error TS2339: Property 'format' does not exist on type 'string | Dayjs'.
  Property 'format' does not exist on type 'string'.

516   query.last_used_before = values[1]?.format('YYYY-MM-DD HH:mm:ss') || '';
                                          ~~~~~
```

影响：

- `vue-tsc -b` 校验失败。
- `pnpm build` 失败。
- 用户管理页面新增的注册日期筛选、最近使用日期筛选无法随版本发布。

## 3. 相关代码位置

文件：

```text
/Users/hua/Documents/project/Reference/SparkService/backoffice-web/src/views/UsersView.vue
```

问题代码：

```ts
function onJoinedRangeChange(values: [Dayjs, Dayjs] | [string, string] | null) {
  if (!values || !Array.isArray(values) || typeof values[0] === 'string') {
    query.date_joined_after = '';
    query.date_joined_before = '';
    return;
  }
  query.date_joined_after = values[0]?.format('YYYY-MM-DD HH:mm:ss') || '';
  query.date_joined_before = values[1]?.format('YYYY-MM-DD HH:mm:ss') || '';
}

function onLastUsedRangeChange(values: [Dayjs, Dayjs] | [string, string] | null) {
  if (!values || !Array.isArray(values) || typeof values[0] === 'string') {
    query.last_used_after = '';
    query.last_used_before = '';
    return;
  }
  query.last_used_after = values[0]?.format('YYYY-MM-DD HH:mm:ss') || '';
  query.last_used_before = values[1]?.format('YYYY-MM-DD HH:mm:ss') || '';
}
```

## 4. 根因分析

`onJoinedRangeChange` 和 `onLastUsedRangeChange` 的入参类型声明为：

```ts
[Dayjs, Dayjs] | [string, string] | null
```

代码里只判断了：

```ts
typeof values[0] === 'string'
```

TypeScript 不能因为 `values[0]` 不是字符串，就推断整个元组一定是 `[Dayjs, Dayjs]`。因此 `values[1]` 仍然被推断为 `string | Dayjs`。

当代码调用：

```ts
values[1]?.format('YYYY-MM-DD HH:mm:ss')
```

TypeScript 认为 `values[1]` 可能是 `string`，而 `string` 没有 `.format()` 方法，所以构建失败。

## 5. 修复目标

- 修复 `UsersView.vue` 的 TypeScript 构建错误。
- 保持注册日期范围筛选功能正常。
- 保持最近使用日期范围筛选功能正常。
- 选择日期后，查询参数格式仍为 `YYYY-MM-DD HH:mm:ss`。
- 清空日期范围后，对应查询参数同步清空。

## 6. 推荐修复方案

建议新增统一格式化函数，兼容 `Dayjs` 和 `string`，避免直接对联合类型调用 `.format()`。

示例：

```ts
function formatRangeDate(value: Dayjs | string | null | undefined) {
  if (!value) {
    return '';
  }
  return typeof value === 'string' ? value : value.format('YYYY-MM-DD HH:mm:ss');
}
```

改造注册日期范围处理：

```ts
function onJoinedRangeChange(values: [Dayjs | string, Dayjs | string] | null) {
  query.date_joined_after = formatRangeDate(values?.[0]);
  query.date_joined_before = formatRangeDate(values?.[1]);
}
```

改造最近使用日期范围处理：

```ts
function onLastUsedRangeChange(values: [Dayjs | string, Dayjs | string] | null) {
  query.last_used_after = formatRangeDate(values?.[0]);
  query.last_used_before = formatRangeDate(values?.[1]);
}
```

## 7. 公共化建议

用户管理、订单、会员、通知、设备等后台列表后续都可能接入日期范围筛选。建议不要在每个页面重复写日期范围格式化逻辑。

可以新增公共工具：

```text
/Users/hua/Documents/project/Reference/SparkService/backoffice-web/src/utils/dateRange.ts
```

建议导出：

```ts
import type { Dayjs } from 'dayjs';

export type AdminRangeDateValue = Dayjs | string | null | undefined;

export function formatAdminDateTimeRangeValue(value: AdminRangeDateValue) {
  if (!value) {
    return '';
  }
  return typeof value === 'string' ? value : value.format('YYYY-MM-DD HH:mm:ss');
}
```

`UsersView.vue` 中使用：

```ts
import { formatAdminDateTimeRangeValue } from '@/utils/dateRange';
```

业务函数只负责赋值：

```ts
function onJoinedRangeChange(values: [Dayjs | string, Dayjs | string] | null) {
  query.date_joined_after = formatAdminDateTimeRangeValue(values?.[0]);
  query.date_joined_before = formatAdminDateTimeRangeValue(values?.[1]);
}
```

## 8. 实现步骤

1. 新增公共日期范围格式化工具，或先在 `UsersView.vue` 内新增局部 helper。
2. 替换 `onJoinedRangeChange` 中对 `values[0]`、`values[1]` 的直接 `.format()` 调用。
3. 替换 `onLastUsedRangeChange` 中对 `values[0]`、`values[1]` 的直接 `.format()` 调用。
4. 确认 `joinedRange`、`lastUsedRange` 的类型和事件处理函数类型一致。
5. 执行构建验证。

## 9. 测试与验收

### 9.1 构建验收

执行：

```bash
cd /Users/hua/Documents/project/Reference/SparkService/backoffice-web
pnpm build
```

验收标准：

- 不再出现 `Property 'format' does not exist on type 'string | Dayjs'`。
- `vue-tsc -b` 通过。
- `vite build` 通过。

### 9.2 功能验收

在用户管理页面验证：

1. 选择注册日期范围后点击查询，请求参数包含：
   - `date_joined_after`
   - `date_joined_before`
2. 选择最近使用日期范围后点击查询，请求参数包含：
   - `last_used_after`
   - `last_used_before`
3. 清空注册日期范围后，注册日期查询参数清空。
4. 清空最近使用日期范围后，最近使用日期查询参数清空。
5. 点击重置后，两个日期选择器和四个日期查询参数全部清空。

## 10. 注意事项

- 不要使用 `as any` 绕过 TypeScript。
- 不要只修复 `values[1]`，两个日期范围函数应统一处理。
- 如果未来 `a-range-picker` 配置 `value-format`，事件值可能变为字符串，公共格式化函数需要继续兼容。
- 本工单不处理部署脚本逻辑。

## 11. 优先级

优先级：P0

原因：

- 当前问题直接导致后台前端构建失败。
- 构建失败会阻断用户管理相关需求发布。

