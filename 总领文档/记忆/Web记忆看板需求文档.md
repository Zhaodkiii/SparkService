# Spark Web 个人记忆看板需求文档

> 文档状态：已确认需求，待实现  
> 更新日期：2026-08-27  
> 范围：`SparkService/chat-web` 用户工作区、`chat_sync` 记忆 API、iOS 同步与聊天 Agent。  
> 约束：本文为目标设计；本次只维护 Markdown，不代表 Web、服务端或客户端代码已实现。  
> 上游：[数据模型文档](./数据模型文档.md)｜[记忆系统与AI工具完整需求文档](./记忆系统与AI工具完整需求文档.md)

## 1. 目标与已确认边界

### 1.1 产品定位

这是**登录用户管理自己长期记忆**的 Web 工作区，不是管理员后台。用户应能知道系统记住了什么、证据来自哪里、哪些内容正在整理，并可以更正、删除或撤销。

功能、信息架构和业务规则对齐 DeepTutor；视觉和组件规范继续使用 Spark Web。服务端数据库是唯一权威源：Web 直接读写服务端，iOS 仅保存镜像、Outbox 和同步游标。Web 不建立平行记忆库。

### 1.2 当前代码事实

| 范围 | 代码证据 | 当前状态 | 目标 |
| --- | --- | --- | --- |
| 记忆路由 | `chat-web/app/(workspace)/memory/page.tsx` | 只有 `FeaturePlaceholder` | 替换为真实个人总览 |
| 侧栏入口 | `chat-web/components/sidebar/WorkspaceSidebar.tsx` | `/memory` 已存在 | 保留入口，接入数据 |
| API 代理 | `chat-web/app/api/v1/[...path]/route.ts` | 已转发 Bearer、幂等键、版本、设备 ID | 复用，不另建通道 |
| Web API 范式 | `chat-web/lib/api/knowledge-api.ts` | 已支持 revision 更新 | 新增同样模式的 `memory-api.ts` |
| 服务端 API | `SparkService/urls.py` | 尚未挂载 memory | 目标 `/api/v1/ai/memory/` |

### 1.3 分期

以下 P1/P2 是 **Web 产品范围**；与《记忆系统与 AI 工具完整需求文档》的全链路实施 P0～P5 不同。Web P1 在全链路计划中随 Workbench 阶段交付。

| 阶段 | 范围 |
| --- | --- |
| P1 | 总览、L1、L2、L3、偏好页、证据追溯、四种工作台任务、运行/撤销、个人设置 |
| P2 | 个人记忆图谱、管理员运营与高级统计 |

## 2. 信息架构

```text
/memory                                  总览
/memory/l1                               L1 证据层
/memory/l1?surface=chat&focus=<traceId>  定位证据
/memory/l2                               L2 领域总结
/memory/l2/[surface]                     L2 文档与工作台
/memory/l3                               L3 长期记忆
/memory/l3/[slot]                        recent/profile/scope/preferences
/memory/resolve?memory_id=<uuid>         安全跳转至条目/证据
/settings/memory                         个人设置
/memory/graph                            P2 图谱
```

### 2.1 三层和来源

| 层 | key | 展示名 | 规则 |
| --- | --- | --- | --- |
| L1/L2 | `chat` | 对话 | 对话、消息和已完成工具调用的最小证据 |
| L1/L2 | `knowledge` | 知识库 | 知识库、文档、检索和引用行为 |
| L1/L2 | `medical` | 医疗资料 | 默认脱敏，遵循敏感确认 |
| L1/L2 | `nutrition` | 营养记录 | 默认脱敏，遵循敏感确认 |
| L1 | `preference` | 偏好事件 | 用户明确表达的回答偏好事件 |
| L3 | `recent` | 近期总结 | 有时间衰减的目标、阶段和变化 |
| L3 | `profile` | 用户画像 | 有多证据支撑的稳定背景或模式 |
| L3 | `scope` | 知识范围 | 熟悉、关注或需更多解释的领域 |
| L3 | `preferences` | 回答偏好 | 仅明确表达、工具写入或用户手动编辑 |

`preference` 是 L1 source，`preferences` 是 L3 slot；前端文案必须区分“偏好事件”和“回答偏好”。

## 3. P1 页面规格

### 3.1 总览 `/memory`

目标：一屏展示开关状态、三层规模、待处理变化和最近工作台运行。

```text
┌──────────────────────────────────────────────────────────────────┐
│ MEMORY  我的记忆                                  [刷新] [设置]  │
│ 了解、查看和管理跨对话持续生效的信息。                           │
│ [记忆已开启]  最近整理：今天 10:21 · 2 项待处理变化             │
├───────────────┬────────────────┬─────────────────────────────────┤
│ L1 证据层      │ L2 领域总结    │ L3 长期记忆                    │
│ 128 条证据     │ 23 条稳定结论  │ 12 条跨场景记忆                │
│ 3 条待处理     │ 最近：对话     │ 最近更新：回答偏好             │
│ [查看证据]     │ [查看总结]     │ [查看长期记忆]                 │
├──────────────────────────────────────────────────────────────────┤
│ 最近任务：update · 对话 · 已完成 · 8 条变更 · 可撤销 [查看]     │
└──────────────────────────────────────────────────────────────────┘
```

数据源：`GET /api/v1/ai/memory/overview/`。

- loading 显示骨架，不能显示伪造的 0。
- empty 说明“与小鲸对话、使用知识库后可生成可审计记忆”。
- disabled 说明不再读取或写入新记忆，历史仍可查看和删除。
- 单个区域失败时保留其余成功区域并局部重试。

### 3.2 L1 证据层 `/memory/l1`

```text
┌──────────────┬────────────────────────────────────────────────────┐
│ 证据来源      │ 对话证据                                [刷新]      │
│ • 对话 40     │ [待处理 3] [全部] [仅失效]                         │
│ • 知识库 18   │ 今天 10:11 用户明确表达偏好             [查看来源]│
│ • 医疗 12     │ “以后请用中文回答” · 已被回答偏好引用             │
│ • 营养 8      │ 昨天 18:20 对话完成 / 内容已脱敏        [查看来源]│
│ • 偏好 2      │ 已关联 2 条对话领域总结                            │
└──────────────┴────────────────────────────────────────────────────┘
```

- L1 是证据，不是已确认结论；不提供编辑或直接写入长期记忆。
- “查看来源”经服务端权限确认后跳转原业务详情；原始数据已删除时显示“来源已删除”，不保留完整原文。
- medical/nutrition 默认只显示裁剪、脱敏摘要。
- 侧栏计数、待处理数和失效状态均由服务端返回，前端不能自行推算。

### 3.3 L2 领域总结 `/memory/l2/[surface]`

```text
┌───────────────┬───────────────────────────────────────────────────┐
│ 领域总结       │ 对话                                               │
│ • 对话 8       │ 上次更新：今天 10:21 · 待处理证据：3             │
│ • 知识库 5     │ [更新] [审计] [去重] [整理结构]                  │
│ • 医疗 4       │ ▾ 回答方式                                       │
│ • 营养 3       │   用户倾向中文和先结论后说明。 [2 条证据] [编辑] │
│                │ 最近任务：audit · 运行中 2/8 · [进度] [取消]   │
└───────────────┴───────────────────────────────────────────────────┘
```

- 每条 L2 必须至少有一个有效 L1 证据；缺证据的条目只能显示异常状态，不能提供给 L3 或 Agent。
- 用户可条目级编辑，不能自由编辑一份 Markdown 文档；保存须通过 revision 和证据校验。
- 同一用户、同一 L2 surface 只允许一个变更型任务；重复点击显示现有运行。

### 3.4 L3 长期记忆 `/memory/l3/[slot]`

```text
┌───────────────┬───────────────────────────────────────────────────┐
│ 长期记忆       │ 回答偏好                                           │
│ • 近期总结 3   │ 只保存你明确告诉小鲸的长期回答偏好。              │
│ • 用户画像 2   │ [新增偏好]                                        │
│ • 知识范围 4   │ • 优先使用中文                       [编辑] [删除]│
│ • 回答偏好 3   │ • 先给结论，再补充依据             [编辑] [删除]│
└───────────────┴───────────────────────────────────────────────────┘
```

| slot | 用户操作 | 工作台操作 | Agent |
| --- | --- | --- | --- |
| `recent` | 编辑、删除、撤销 | update/audit/dedup/merge | 按需读取 |
| `profile` | 编辑、删除、撤销 | 多证据 update/audit/dedup/merge | 按需读取 |
| `scope` | 编辑、删除、撤销 | 不得由单轮得出绝对判断 | 按需读取 |
| `preferences` | 新增、编辑、删除、撤销 | 只允许 dedup/merge | 按需读取 |

页面须明确提示：长期记忆只会在适合的对话中被 AI 按需读取，不是每轮必读。

### 3.5 工作台运行抽屉

从 L2/L3 页面打开，展示模式、目标、阶段事件、进度、错误、取消和撤销。

```text
┌──────────────────────────────────────────────────────────┐
│ 整理对话记忆                                      [关闭] │
│ 模式：更新   依据：3 条新增证据   状态：运行中           │
│ ● 收集证据  ✓ 生成候选  ○ 校验引用  ○ 应用变更          │
│ 10:21:03 收集 3 条新证据                                 │
│ 10:21:12 生成 add/edit 操作                              │
│ [取消运行]     完成后可撤销                              │
└──────────────────────────────────────────────────────────┘
```

状态机：`queued → running → applying → succeeded | failed | cancelled`；`succeeded → undoing → undone`。页面关闭不取消任务，重新进入以 `run_id + after_sequence` 恢复。

### 3.6 个人设置 `/settings/memory`

| 设置 | 默认建议 | 效果 |
| --- | --- | --- |
| 启用长期记忆 | 开启 | 关闭后不挂载记忆工具、不读取 L3 |
| 允许 AI 保存明确偏好 | 开启 | 关闭后拒绝 `write_memory` |
| 允许跨对话使用记忆 | 开启 | 关闭后禁用跨 thread `read_memory` |
| 自动整理记忆 | 关闭 | 仅触发受控异步任务 |
| 使用医疗资料作为证据 | 待合规确认 | 控制 medical/nutrition 是否参与整理 |

模型、Token、分块、并发和成本预算是服务端/管理员技术配置，不对普通用户开放。保存使用 `If-Match`，冲突时回显服务端版本。

## 4. 前端落地结构与状态

```text
chat-web/
├── app/(workspace)/memory/
│   ├── page.tsx
│   ├── l1/page.tsx
│   ├── l2/page.tsx
│   ├── l2/[surface]/page.tsx
│   ├── l3/page.tsx
│   ├── l3/[slot]/page.tsx
│   └── resolve/page.tsx
├── app/(workspace)/settings/memory/page.tsx
├── components/memory/
│   ├── MemoryOverview.tsx
│   ├── MemorySourceRail.tsx
│   ├── MemoryEntryList.tsx
│   ├── MemoryEntryEditor.tsx
│   ├── MemoryEvidenceDrawer.tsx
│   ├── MemoryRunPanel.tsx
│   ├── MemoryRunTimeline.tsx
│   └── MemorySettingsForm.tsx
├── lib/api/memory-api.ts
└── types/memory.ts
```

以上是目标目录。页面只维护加载、展示和短暂编辑草稿；权限、去重、版本、任务状态转换和并发均由服务端决定。

| 模块 | 必须状态 |
| --- | --- |
| Overview | loading、ready、empty、partial_error、disabled |
| L1 | loading、ready、empty、source_deleted、error |
| L2/L3 | loading、ready、editing、saving、conflict、error |
| Run | idle、queued、running、applying、succeeded、failed、cancelled、undoing、undone |
| Settings | loading、ready、saving、conflict、error |

`SparkMemoryApi` 复用 `SparkHttpClient`：创建/启动任务带 `Idempotency-Key`；编辑/删除/设置带 `If-Match`；冲突时放弃旧草稿，展示服务端快照；不得在 localStorage 持久化记忆或证据正文。

## 5. 服务端接口契约（目标）

统一前缀：`/api/v1/ai/memory/`。所有接口从认证身份取得用户，不信任请求中的 `user_id`。

| Method | Path | 目的 |
| --- | --- | --- |
| GET | `overview/` | 三层摘要、backlog、最近 Run、设置摘要 |
| GET | `documents/` | L2/L3 文档摘要 |
| GET | `documents/{layer}/{key}/entries/` | 条目分页与文档 revision |
| GET/PATCH | `settings/` | 读取/更新个人设置 |
| POST | `entries/` | 仅允许用户新增 `L3/preferences` |
| PATCH/DELETE | `entries/{memory_id}/` | 条目级编辑、软删除、revision 校验 |
| GET | `entries/{memory_id}/evidence/` | 最小引用和脱敏摘要 |
| POST | `changes/{change_set_id}/undo/` | 在撤销期内回滚 |
| POST | `runs/` | 创建 update/audit/dedup/merge 异步任务 |
| GET | `runs/{run_id}/` | 获取任务最终状态 |
| GET | `runs/{run_id}/events/?after_sequence=` | SSE 主通道或增量轮询兜底 |
| POST | `runs/{run_id}/cancel/` | 请求取消 |
| POST | `runs/{run_id}/undo/` | 撤销成功任务的 ChangeSet |
| GET | `traces/?surface=&cursor=` | L1 Trace 分页 |
| GET | `traces/{trace_id}/` | Trace 元数据和可见摘要 |
| POST | `traces/{surface}/refresh/` | 异步刷新快照 |

建议稳定错误：`memory.revision_conflict`、`memory.run_active`、`memory.run_not_cancellable`、`memory.preference_only`、`memory.evidence_required`、`memory.source_deleted`、`memory.settings_conflict`。所有响应沿用统一包裹和 request ID。

## 6. 工作台、权限与安全规则

| 模式 | 输入 | 输出 | 限制 |
| --- | --- | --- | --- |
| update | L1 新 Trace 或 L2 新版本 | add/edit 操作 | 不写 preferences；必须有引用 |
| audit | 现有条目和证据 | 修正、降级、删除 | 不自动改写 preferences |
| dedup | 同文档有效条目 | 合并重复项和证据 | 保留稳定 ID |
| merge | 分组、排序、引用 | 确定性结构整理 | 不改变事实语义 |

```text
创建 Run（幂等）
  → Celery 异步执行并写 RunEvent
  → AI 生成受限 Operation 候选
  → 服务端校验权限、引用、长度、去重、base revision
  → 单事务写 Memory / Evidence / DocumentState / ChangeSet
  → Web 刷新列表和总览；用户可撤销
```

- AI 和前端都不能绕过领域服务直接写表。
- 同一 `user_id + layer + document_key` 最多一个变更型 Run；不同文档可有限并行。
- 任务失败、断线或模型不可用不影响聊天、登录、启动、知识库和客户端同步。
- 删除为 tombstone：立即不能被 `read_memory` 使用，并同步给其他设备；建议默认保留 30 天，最终由隐私策略确认。
- 原业务数据删除后，L1 标记来源失效，关联 L2/L3 进入审计候选，不保留完整原文。
- 日志只记录 ID、状态、计数、耗时、request ID、错误码；禁止正文、证据正文、structured value 和模型原始输出。

## 7. AI 工具和多端同步

- `read_memory` 读取当前发布、有效、可见的 L3；模型按需调用。
- `write_memory` 仅新增/编辑用户明确表达的 `L3/preferences`，同时写 `preference_stated` L1 Trace。
- Web 偏好页和 `write_memory` 必须复用同一领域服务，保证聊天保存后看板立即可见。
- Web 无独立 Outbox；Web 写成功即成为权威快照。iOS 以 `memory_id + revision + mutation_id` Push/Pull，同冲突以服务端快照覆盖客户端。
- 设置同样以服务端 revision 为准，Web 与 iOS 看到同一结果。

## 8. 数据模型影响

看板不引入 Web 专用主表，依赖上游模型：

| 模型 | 看板使用 |
| --- | --- |
| `AIMemorySettings` | 个人隐私开关、revision |
| `AIMemoryTraceEvent` | L1 列表、脱敏摘要、来源失效状态 |
| `AIMemory` / `AIMemoryEvidence` | L2/L3 条目、证据抽屉和条目版本 |
| `AIMemoryDocumentState` | backlog、文档 revision、活动任务、最近成功运行 |
| `AIMemoryRun/Event/ChangeSet` | 运行进度、恢复、取消、撤销 |

`AIMemoryDocumentState` 是 L2/L3 聚合状态的唯一来源；前端不能以计数、浏览器时间或缓存推算 backlog、版本和运行锁。

## 9. 验收与待确认

### 9.1 P1 验收

- [ ] `/memory` 不再显示占位页，展示本人真实三层摘要。
- [ ] L1 支持五类来源；敏感证据脱敏，删除来源正确失效。
- [ ] L2/L3 支持条目级编辑、证据追溯、revision 冲突处理。
- [ ] 四种工作台模式可启动、断线恢复、取消、失败提示和撤销，重复点击不重复创建 Run。
- [ ] 偏好可增删改，且 update/audit 不会推断或改写。
- [ ] 个人设置实际控制工具挂载与跨会话读取，并可同步至 iOS。
- [ ] Web、`write_memory`、iOS 同步最终都读取同一服务端版本。
- [ ] 失败不阻断聊天、登录、启动或知识库同步；日志不泄露正文。

### 9.2 仍需最终确认

1. medical/nutrition 是否默认参与自动整理，还是默认关闭、由用户显式授权。
2. tombstone 与 ChangeSet 实际保留期；本文建议 30 天。
3. P1 聊天工具活动是否向用户展示“本轮读取了记忆”。
4. P1 直接交付 SSE，还是先用 `after_sequence` 轮询；无论哪种都保留重放接口。
5. P2 图谱优先级以及管理员查看正文的最终 RBAC、访问理由和审计规范。
