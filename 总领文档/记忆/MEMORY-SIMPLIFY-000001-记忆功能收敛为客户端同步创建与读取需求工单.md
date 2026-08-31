# MEMORY-SIMPLIFY-000001 记忆功能收敛为客户端同步、创建与读取需求工单

## 1. 工单信息

- 工单编号：`MEMORY-SIMPLIFY-000001`
- 创建日期：2026-08-29
- 状态：待开发
- 类型：跨端功能删减 / 破坏性接口收敛
- 涉及项目：SparkService、chat-web、SparkClient iOS
- 本工单只定义删减范围，不在本次文档创建中修改任何业务代码。

## 2. 一句话目标

记忆功能只保留三件事：客户端同步记忆、创建记忆、读取记忆；删除工作台整理、自动归纳、更新、删除、证据、Trace、撤销、设置中心及全部记忆相关服务端异步任务。

## 3. 最终产品形态

用户只能：

1. 在 Web 或 iOS 创建一条记忆。
2. 查看自己的记忆列表和单条内容。
3. 由 iOS 在登录账号下同步本地记忆与服务端记忆。
4. 在对话中允许 AI 调用“保存记忆”和“读取记忆”。

用户不能：

1. 编辑或删除单条记忆。
2. 运行 `update / audit / dedup / merge` 整理任务。
3. 查看 L1/L2/L3、来源 Trace、证据、整理进度或 ChangeSet。
4. 撤销整理结果。
5. 配置记忆工作台、敏感证据、跨线程整理等高级开关。

## 4. 保留范围

### 4.1 服务端保留

保留最小数据能力：

- `AIMemory`：记忆主记录。
- `AIMemoryMutationReceipt`：客户端创建请求的幂等回执。若实现改为由 `AIMemory` 唯一键直接保证幂等，可在后续迁移中再删除该表，本工单不强制。
- 创建记忆：`POST /api/v1/ai/memory/entries/`。
- 读取列表：`GET /api/v1/ai/memory/entries/`。
- 读取单条：`GET /api/v1/ai/memory/entries/{memory_id}/`。
- 客户端同步上传：`POST /api/v1/ai/memory/sync/push/`，只接受 `create`。
- 客户端同步拉取：`GET /api/v1/ai/memory/sync/pull/`。
- 服务端 AI 工具：保留 `read_memory`。
- 服务端 AI 工具：保留 `write_memory`，但只允许创建，不允许 `edit`。
- 账号删除时继续通过外键级联删除该账号的所有记忆。

保留的创建请求至少包含：

- `memory_id`
- `content`
- `title`（可选）
- `created_at`
- `mutation_id` 或等价幂等键

读取结果只返回记忆本身需要的字段，不再返回 evidence、trace、run、change set 或整理状态。

### 4.2 Web 保留

保留一个极简记忆页：

- 记忆列表。
- 单条记忆只读展示。
- “新建记忆”入口和表单。
- 创建成功后刷新列表。
- 空状态、加载状态、创建失败提示。

Web 不承担客户端离线同步，不保留工作台概念。

### 4.3 iOS 保留

保留：

- 本地记忆存储。
- 本地创建记忆。
- 本地列表和读取。
- `MemorySyncOutboxStore`、`MemoryOutboxPipeline`、`MemorySyncEngine`、`MemorySyncSupervisor`。
- `SparkMemoryRemoteAPI` 的 `sync/push` 与 `sync/pull`。
- `SaveMemoryUseCase`、`RetrieveMemoryUseCase`。
- `ToolHubSaveMemory`、`ToolHubRetrieveMemory`。
- 登录、App 启动、回前台及本地创建后的必要同步触发。

iOS 的 Swift `async/await` 网络执行属于客户端同步实现，不属于本工单要求删除的“服务端异步任务”。

## 5. 完整移除范围

### 5.1 服务端异步任务全部移除

删除 `chat_sync/ai_tasks/memory_tasks.py` 中全部任务：

- `run_memory_workbench`
- `expire_memories`
- `purge_memory_receipts`
- `repair_stale_memory_runs`
- `purge_memory_changesets`

同时移除：

- `SparkService/celery.py` 中 `chat_sync.ai_tasks.memory_tasks` 的导入登记。
- `SparkService/settings.py` 中全部 `chat_sync.ai_tasks.memory_tasks.*` 路由。
- `CELERY_BEAT_SCHEDULE` 中全部 `memory-*` 周期任务。
- 后台异步任务管理页面中的记忆任务注册项。
- 与这些任务对应的测试、健康检查、队列说明和部署文档。

验收要求：

```bash
rg "chat_sync\.ai_tasks\.memory_tasks|run_memory_workbench|expire_memories|purge_memory_receipts|repair_stale_memory_runs|purge_memory_changesets" SparkService chat_sync backoffice
```

除历史迁移说明或本工单外，不得再有运行时代码命中。

### 5.2 服务端工作台引擎移除

删除以下服务：

- `memory_consolidator.py`
- `memory_operation_service.py`
- `memory_run_service.py`
- `memory_workbench_runner.py`
- `memory_trace_service.py`
- `memory_overview_service.py`
- `memory_settings_service.py`

删除以下数据模型及对应运行时导出：

- `AIMemoryRun`
- `AIMemoryRunEvent`
- `AIMemoryChangeSet`
- `AIMemoryTraceEvent`
- `AIMemoryEvidence`
- `AIMemoryDocumentState`
- `AIMemorySettings`

删除以下概念：

- L1 / L2 / L3 分层工作台。
- `update / audit / dedup / merge` Run 模式。
- Run 状态机、认领、取消、事件轮询和卡住恢复。
- 模型 Consolidator 和受限 JSON 操作生成。
- Apply、Undo、ChangeSet 和撤销窗口。
- Trace 来源、证据引用、backlog、敏感来源开关。
- 记忆自动过期。简化后记忆不会由定时任务自动失效。

需要新增数据库迁移删除上述表或字段。迁移不得删除 `AIMemory` 主数据。上线前必须先备份相关表，并确认不需要保留工作台历史。

### 5.3 服务端接口移除

删除：

- `/overview/`
- `/settings/`
- `/documents/`
- `/documents/{layer}/{document_key}/entries/`
- `/entries/{memory_id}/evidence/`
- `/traces/` 及所有 Trace 子路由
- `/runs/` 及所有 Run 子路由
- `/changes/{change_set_id}/undo/`
- `PATCH /entries/{memory_id}/`
- `DELETE /entries/{memory_id}/`

保留后的路由只能包含：

```text
GET  /api/v1/ai/memory/entries/
POST /api/v1/ai/memory/entries/
GET  /api/v1/ai/memory/entries/{memory_id}/
POST /api/v1/ai/memory/sync/push/
GET  /api/v1/ai/memory/sync/pull/
```

`sync/push` 只接受 `create`。旧客户端提交 `update / delete / restore` 时返回稳定的“不支持”业务码，不得静默接受。

### 5.4 对话与知识库耦合移除

删除以下自动 Trace 写入：

- Chat Run 完成后写入 `MemoryTraceService.record_chat_event`。
- 知识库检索命中后写入 `MemoryTraceService.record_knowledge_citation`。
- 创建记忆后写入 preference trace 或 evidence。
- `context_builder.py` 中基于 Memory Settings 动态判断工具可用性的逻辑。

保留对话工具：

- `read_memory`：读取已有记忆。
- `write_memory`：只创建新记忆。

删除 `write_memory` 的 `edit` 参数、目标记忆 ID、修改逻辑和对应测试。AI 不再自动整理、合并、修改或删除既有记忆。

简化后不再读取 `AIMemorySettings`：`read_memory` 与 create-only `write_memory` 是否挂载，只由现有服务端工具清单/场景配置决定，不再叠加记忆专属设置开关。

### 5.5 Web 移除

删除页面：

- `/memory/l1`
- `/memory/l2`
- `/memory/l2/[surface]`
- `/memory/l3`
- `/memory/l3/[slot]`
- `/memory/resolve`
- `/settings/memory`

删除组件：

- `MemoryOverview`
- `MemoryDocumentWorkspace`
- `MemoryEvidenceDrawer`
- `MemoryRunPanel`
- `MemoryRunTimeline`
- `MemorySettingsForm`
- `MemorySourceRail`
- 所有编辑、删除、整理、审计、去重、合并和撤销控件

重写而不是整体删除：

- `/memory/page.tsx`：改为极简列表 + 创建入口。
- `lib/api/memory-api.ts`：只保留 entries 的 GET/POST/GET detail。
- `types/memory.ts`：只保留 MemoryEntry、创建参数和分页类型。
- `MemoryEntryList`、`MemoryEntryEditor`：收敛为只读列表与“仅新建”表单；不得出现编辑模式。

同步移除侧边栏或设置首页中指向已删除记忆子页面的链接。侧边栏 `/memory` 主入口保留。

### 5.6 iOS 移除

删除能力：

- `UpdateMemoryUseCase`
- `DeleteMemoryUseCase`
- `ToolHubUpdateMemory`
- ToolHub 中 `.updateMemory` 路由、依赖注入和工具定义
- `MemoryRepository.update`
- `MemoryRepository.updateMatching`
- `MemoryRepository.delete`
- `MemoryRepository.deleteAll`
- 设置页中的编辑、删除、全部删除和高级开关
- `SparkMemoryRemoteAPI` 的 settings GET/PATCH
- 本地 settings 同步模型及仅为高级开关存在的实体字段

保留并收窄：

- `MemoryRepository.list`
- `MemoryRepository.save`
- `MemoryRepository.retrieve`
- 客户端同步所需的本地实体、cursor 和 outbox
- `MemorySyncOperation` 只允许 `.create`
- `MemoryArchiveSettingsView` 改为“记忆列表 + 新建 + 只读详情”；若产品不需要设置入口，可更名为 `MemoryView`，但路由必须保持稳定或提供迁移入口

AppContainer、AssemblyProducts、ToolHub 构造函数和测试中的 update/delete 依赖一并移除。

## 6. 数据与兼容策略

### 6.1 已有记忆

- 保留所有未删除的 `AIMemory`。
- 已删除 tombstone 是否保留由迁移前数据检查决定；默认保留到旧客户端最低支持版本退出后再清理。
- 不把 Trace、Evidence 或 ChangeSet 自动转换成新的记忆。
- 不运行最后一次 Consolidator。

### 6.2 旧客户端

- 发布顺序：服务端兼容版本 → iOS 简化版本 → Web 简化版本 → 移除旧接口版本。
- 兼容窗口内可让旧接口返回明确弃用错误，但不得继续启动工作台 Run。
- 旧客户端发送更新、删除 mutation 时必须得到可识别错误，避免无限重试；iOS 新版收到该错误后应把旧 Outbox 项标记为永久失败并停止重试。

### 6.3 重要产品限制

本工单按“只创建、只读取”执行后，用户不能修改或单独删除错误记忆。账号注销仍会删除全部数据，但这不等价于单条删除。产品负责人必须在开发前书面确认接受该限制；若不接受，应把“用户手动删除”加入最小保留能力，但不得恢复工作台、自动整理或异步任务。

## 7. 实施顺序

### 阶段 A：停止产生复杂数据

1. 禁止创建新的 Memory Run。
2. 停止 Chat、Knowledge 和 preference Trace 写入。
3. 停止全部记忆 Celery 和 Beat 任务。
4. 将 `write_memory` 限制为 create。

### 阶段 B：收敛 API 与客户端

1. 服务端保留最小 entries + sync API。
2. iOS 更新为 create-only Outbox，移除更新和删除入口。
3. Web 改为列表、读取、新建。
4. 移除无效导航、类型和接口调用。

### 阶段 C：删除工作台数据结构

1. 确认线上不再有活动 Run。
2. 备份 Run、Trace、Evidence、ChangeSet 表。
3. 执行删除模型的数据库迁移。
4. 删除工作台服务、任务和测试。
5. 执行跨端回归。

## 8. 验收标准

### 8.1 功能验收

- Web 可以创建记忆并立即在列表中读取。
- iOS 可以离线创建记忆，联网后同步到服务端。
- 同账号另一台 iOS 设备可以 pull 到该记忆。
- AI 可以创建记忆。
- AI 可以读取记忆。
- AI 不能编辑、删除、合并或整理记忆。
- Web 和 iOS 均没有编辑、删除、整理、Trace、证据、撤销和高级设置入口。

### 8.2 异步任务验收

- Celery 注册任务中不存在任何 `chat_sync.ai_tasks.memory_tasks.*`。
- Celery Beat 中不存在任何 `memory-*` 调度。
- 创建和读取记忆不依赖 Celery worker。
- 停止 Celery worker 后，Web 创建/读取和 iOS push/pull 仍正常工作。
- iOS 客户端同步仍通过本地异步网络流程执行。

### 8.3 数据验收

- 迁移前后的 `AIMemory` 有效记录数一致。
- 不再新增 Run、RunEvent、Trace、Evidence、ChangeSet 记录。
- 同一 `mutation_id` 重试创建不会产生重复记忆。
- 不同账号不能读取彼此记忆。

### 8.4 删除完整性检查

除迁移、历史文档和本工单外，运行时代码不得再命中：

```text
MemoryRun
MemoryTrace
MemoryEvidence
MemoryChangeSet
MemoryDocumentState
memory_workbench
memory_consolidator
updateMemory
deleteMemory
run_memory_workbench
expire_memories
repair_stale_memory_runs
```

## 9. 测试范围

### 服务端

- 创建成功、空内容失败、越权失败。
- 列表分页、单条读取、账号隔离。
- create mutation 幂等重放。
- update/delete mutation 返回稳定不支持错误。
- 无 Celery worker 时 API 正常。
- 路由中不存在工作台、Trace、Evidence、Settings 和 Undo 接口。

### Web

- 列表、空状态、错误状态。
- 新建表单校验及幂等提交。
- 创建后刷新并显示。
- 已删除路由返回 404，不再出现死链接。

### iOS

- 本地创建和读取。
- 离线创建后恢复联网自动上传。
- 多设备 pull。
- 重复 push 不产生重复记录。
- 账号切换时 cursor、outbox 和本地记录隔离。
- 不存在更新、删除、设置同步及 update-memory 工具入口。

## 10. 非目标

- 不重设计知识库。
- 不修改聊天 Run 和聊天事件 Outbox。
- 不新增记忆向量检索。
- 不新增记忆自动摘要。
- 不新增后台管理页面。
- 不新增 Android 实现。
- 不在本工单创建阶段修改任何代码或数据库。

## 11. 完成定义

只有以下条件全部满足，工单才能关闭：

1. 生产运行时只剩记忆创建、读取和 iOS 客户端同步。
2. 记忆相关 Celery 与 Beat 任务全部删除。
3. 工作台、自动整理、更新、删除、Trace、Evidence、Undo 和 Settings 全部不可达。
4. Web、服务端、iOS 的契约和界面一致。
5. 现有记忆主数据没有因删减迁移丢失。
6. 文档、测试和部署配置不再宣称支持已删除能力。
