# KNOWLEDGE-SIMPLIFY-000003 知识库收敛为客户端同步与基础增删改查需求工单

## 1. 工单信息

- 工单编号：`KNOWLEDGE-SIMPLIFY-000003`
- 创建日期：2026-08-29
- 状态：待开发
- 类型：Web 与服务端功能删减 / iOS 兼容性保护
- 涉及改动项目：SparkService、chat-web
- 明确不改动项目：SparkClient iOS
- 关联工单：`KNOWLEDGE-SYNC-000001`、`KNOWLEDGE-CHAT-000002`、`MEMORY-SIMPLIFY-000001`
- 本工单只制定计划和删除范围，不在本次文档创建中修改任何业务代码。

## 2. 一句话目标

Web 与服务端知识库收敛为知识库/文档的创建、读取、编辑、删除，并兼容现有 iOS 客户端同步；删除服务端文件导入、索引、切块、Embedding、RAG、AI 对话接入及全部知识库异步任务，但不修改任何 iOS 代码、界面、本地能力或同步协议。

## 3. 最终产品形态

用户可以：

1. 在 Web 创建知识库。
2. 在 Web 查看知识库列表和单个知识库。
3. 在 Web 知识库中创建纯文本文档。
4. 在 Web 查看文档列表和文档正文。
5. 在 Web 编辑、删除知识库和知识文档。
6. 现有 iOS 继续使用原有知识库能力和同步流程，不要求发版配合本工单。
7. Web 按标题或正文做普通文本过滤；该过滤不调用模型、不生成服务端索引。

用户不能：

1. Web 上传 PDF、DOCX、Markdown 等文件并自动提取。
2. Web 或服务端建立、重建索引。
3. Web 或服务端使用向量、Embedding、RAG 或语义搜索。
4. Web 对话中选择知识库或让服务端 AI 调用知识库检索工具。
5. Web 查看文件处理状态、索引状态、索引版本、引用卡片或检索审计。

iOS 不受以上产品删减约束；iOS 当前已有的创建、读取、更新、删除、本地搜索、本地 Embedding、文件导入、ToolHub 和同步能力全部保持原样。

## 4. 保留范围

### 4.1 服务端数据模型

保留：

- `KnowledgeBase`：知识库容器。
- `KnowledgeDocument`：纯文本知识文档。
- `KnowledgeMutationReceipt`：现有 iOS `create / update / delete / restore` mutation 的幂等回执，必须保持兼容。
- `KnowledgeCommandReceipt`：Web 创建知识库的幂等回执。若 Web 创建文档也统一使用客户端 mutation 协议，可后续合并，不在本工单强制。

`KnowledgeBase` 收敛字段：

- 保留 `id`、`user`、`name`、`kind`、`is_default`、`default_slot`、`revision`、创建和更新时间。
- 删除 `retrieval_config`。
- 保留 `is_deleted`、`deleted_at`，用于 Web 删除和 iOS tombstone 同步。

`KnowledgeDocument` 收敛字段：

- 保留 `id`、`user`、`knowledge_base`、`title`、`content`、`excerpt`、`revision`、`content_hash`、客户端/服务端时间和同步所需设备哈希。
- `scope`、`bound_model_id`、`source_file_uuid` 及其他 iOS 同步 DTO 已使用的字段必须保留；只有确认 iOS 完全未读取、未写入的服务端派生字段才可删除。
- 保留 `is_deleted`、`deleted_at`，用于 Web 删除和 iOS tombstone 拉取。

### 4.2 服务端接口

保留：

```text
GET  /api/v1/ai/knowledge/default/
GET  /api/v1/ai/knowledge/bases/
POST /api/v1/ai/knowledge/bases/
GET  /api/v1/ai/knowledge/bases/{base_id}/
PATCH /api/v1/ai/knowledge/bases/{base_id}/
DELETE /api/v1/ai/knowledge/bases/{base_id}/
GET  /api/v1/ai/knowledge/bases/{base_id}/documents/
POST /api/v1/ai/knowledge/bases/{base_id}/documents/
GET  /api/v1/ai/knowledge/documents/{document_id}/
PATCH /api/v1/ai/knowledge/documents/{document_id}/
DELETE /api/v1/ai/knowledge/documents/{document_id}/
POST /api/v1/ai/knowledge/sync/push/
GET  /api/v1/ai/knowledge/sync/pull/
```

约束：

- `sync/push` 必须继续接受现有 iOS 已使用的 `create / update / delete / restore` 文档 mutation，响应结构和错误码保持兼容。
- 创建文档只接受纯文本标题和正文。
- 创建文档不得触发索引、文件解析、Embedding、Celery 或模型调用。
- Web 编辑和删除必须使用 revision / `If-Match` 做并发控制；冲突返回当前服务端快照。
- 删除采用 tombstone 软删除，保证 iOS 增量 pull 能同步删除状态。
- 列表查询可提供普通 `q` 参数，但只允许数据库文本过滤，不允许语义检索。
- 读取 DTO 不再返回 `index_state`、`retrieval_config`、`source_file` 或索引统计。

### 4.3 Web

保留：

- `/knowledge`：知识库列表和新建知识库。
- `/knowledge/[knowledgeBaseId]`：知识文档列表、创建、读取、编辑和删除。
- 侧边栏“知识库”入口。
- 空状态、加载状态、创建失败、读取失败和分页。
- 标题/正文普通文本过滤。

Web 不实现离线同步，不显示任何索引或 AI 能力。

### 4.4 iOS：完整冻结，不改动

本工单不得修改 `/Users/hua/Documents/project/Reference/LookHealthClient/SparkClient` 下任何 iOS 文件，包括但不限于：

- Swift 业务代码、UI、UseCase、Repository、ToolHub 和依赖注入。
- CoreData 模型、Chunk、Embedding 和本地搜索。
- 文件导入、文档编辑、删除和重新索引。
- `KnowledgeSyncOutboxStore`、`KnowledgeSyncEngine`、`KnowledgeSyncSupervisor`。
- `SparkKnowledgeRemoteAPI`、同步 DTO、cursor 和 mutation 类型。
- iOS 测试、工程配置、资源和文案。

服务端删减必须以“现有 iOS 无需改动、无需发版、同步不降级”为硬约束。iOS 的现有 Swift `async/await` 网络同步不属于服务端异步任务。

## 5. 完整移除范围

### 5.1 服务端异步任务全部移除

删除 `chat_sync/ai_tasks/knowledge_tasks.py` 中全部任务：

- `index_document_task`
- `rebuild_index_version_task`
- `extract_document_task`

同时删除：

- `SparkService/celery.py` 中 `chat_sync.ai_tasks.knowledge_tasks` 的导入登记。
- `SparkService/settings.py` 中三项 knowledge task queue route。
- 后台异步任务管理器中的三项 AI 知识库任务。
- 对应任务测试、任务说明、健康检查和部署配置。

验收命令：

```bash
rg "chat_sync\.ai_tasks\.knowledge_tasks|index_document_task|rebuild_index_version_task|extract_document_task" SparkService chat_sync backoffice
```

除历史迁移、历史文档和本工单外，不得再有运行时代码命中。

### 5.2 服务端索引与检索引擎移除

删除目录或模块：

- `ai_knowledge/retrieval/`
- `services/index_jobs.py`
- `services/index_pipeline.py`
- `services/chunker.py`
- `services/extractors.py`
- `services/file_service.py`
- `ai_runtime/tools/adapters/search_knowledge_bag.py`

删除模型：

- `KnowledgeChunk`
- `KnowledgeIndexState`
- `KnowledgeIndexVersion`
- `KnowledgeRetrievalAudit`

删除配置：

- `KNOWLEDGE_FILE_IMPORT_ENABLED`
- `KNOWLEDGE_CHAT_SELECTOR_ENABLED`
- `KNOWLEDGE_RAG_TOOL_ENABLED`
- `KNOWLEDGE_DEEPTUTOR_ADAPTER_ENABLED`
- 与 chunk 大小、chunk 上限、Embedding、检索阈值、索引版本相关的知识库配置

删除行为：

- 文档 create 后的 `_schedule_index`。
- 文档同步后的 `enqueue_document_index`。
- 文件提取和文件绑定。
- Chunk 生成和存储。
- 文档和 query 的 Embedding 调用。
- 余弦相似度和词法降级检索服务。
- 检索引用、citation DTO 和检索审计记录。
- 整库 rebuild 和 active index version。

### 5.3 服务端接口移除

删除：

- `/bases/{base_id}/files/` 及子路由
- `/bases/{base_id}/index-versions/`
- `/bases/{base_id}/index-jobs/`
- `/search/`

旧客户端调用已删除接口时应收到稳定的“不支持”业务码。兼容窗口结束后路由直接移除。

### 5.4 与聊天和 AI 的知识库耦合全部移除

删除：

- Web 对话工具栏中的 `KnowledgeSelector`。
- Thread Preferences 的 `knowledge_bases` 产品入口；数据字段可在协议兼容窗口保留为空数组，随后迁移删除。
- `context_builder.py` 中 `freeze_knowledge_bases`、`eligible_base_ids` 和 `search_knowledge_bag` 自动工具挂载。
- `ChatTurnContextSnapshot.sources` 中 knowledge base 冻结元数据。
- `search_knowledge_bag` 服务端工具定义、注册、策略、公开投影和测试。
- Web Knowledge citation 卡片和其专用展示数据。

完成后，Web 与服务端知识库不再参与服务端 AI 对话上下文或服务端工具调用。iOS ToolHub 的 `.searchKnowledgeBag`、`.createKnowledgeDocument` 及其本地执行逻辑保持原样。

### 5.5 Web 移除

删除组件：

- `KnowledgeFilesTab`
- `KnowledgeIndexVersionsSection`
- `KnowledgeSettingsSection`
- `KnowledgeSelector`
- 检索参数设置和重建入口

收敛组件：

- `CreateKbModal`：只保留知识库名称，不提交 `retrieval_config` 或高级设置。
- `KnowledgeBaseCard`：显示名称、文档数量及编辑/删除操作，不显示 index/sync/file 状态。
- `KnowledgeDocumentList`：显示文档，并提供读取、编辑和删除操作。
- `KnowledgeDocumentEditor`：支持创建与编辑纯文本文档；编辑提交必须携带 revision。
- `/knowledge/[knowledgeBaseId]/page.tsx`：删除 files/index/settings tabs，保留文档列表、创建、读取、编辑和删除。
- `knowledge-api.ts`：只保留工单第 4.2 节列出的 API。
- `types/knowledge.ts`：删除 Index、File、Citation、RetrievalConfig 类型。

页面文案不得再出现“对话引用、后台索引、语义检索、索引就绪”等描述。

### 5.6 iOS 不在移除范围

本工单不得删除、调整或重构任何 iOS 知识库能力。即使 iOS 当前仍包含本地 Chunk、Embedding、搜索、更新、删除、文件导入、重建索引和 AI 工具，也全部保留。

实施者不得为了清理服务端或 Web 编译错误而顺带修改 iOS。若服务端删减与现有 iOS 契约冲突，必须调整服务端方案或停止该删除项，不能要求 iOS 配合修改。

## 6. 数据迁移与兼容策略

### 6.1 主数据保护

- 不删除 `KnowledgeBase` 和 `KnowledgeDocument` 主数据。
- 删除索引表前记录各表行数并完成数据库备份。
- `KnowledgeChunk`、IndexState、IndexVersion 和 RetrievalAudit 属于派生数据，可在备份后删除，不转换为正文。
- `source_file_uuid` 关联的已有文档：若正文已经提取到 `KnowledgeDocument.content`，保留正文并解除文件功能；若正文为空，必须先生成“无法迁移文件内容”清单，不得静默留下空文档。
- 不执行任何 iOS CoreData 迁移，不删除 iOS Chunk、Embedding 或同步字段。

### 6.2 旧客户端

- 发布顺序：服务端兼容版本 → Web 简化版本 → 服务端确认 iOS 回归通过后再删除纯服务端派生表；不安排 iOS 发版。
- 服务端停止实际索引任务后，iOS 已使用的响应字段必须继续返回契约兼容值；不得要求 iOS 修改 DTO。
- iOS Outbox 中的 `create / update / delete / restore` mutation 必须继续正常处理，不能标记为不支持。
- 旧客户端请求搜索、重建或文件导入时返回明确弃用错误，不能返回“已受理”假状态。

### 6.3 产品限制

本工单实施后：

- Web 与服务端知识库不再帮助服务端 AI 回答问题。
- Web 用户不能导入文件，只能输入纯文本。
- iOS 原有功能和交互不变。
- 账号注销仍通过外键级联删除全部知识库数据。

Web 用户保留知识库和文档的编辑、删除权。产品负责人必须确认其余限制仅适用于 Web 与服务端高级能力，不得据此删减 iOS。

## 7. 制定实施计划

### 阶段 A：立即停止复杂链路

1. 禁止创建新的索引和 rebuild job。
2. 停止三项 knowledge Celery 任务及任务登记。
3. 文档 create/sync 不再调用 `_schedule_index`。
4. 关闭知识库文件导入、聊天选择器和 RAG 工具。
5. 旧接口改为明确弃用响应，不再产生派生数据。

完成条件：创建和同步纯文本文档不依赖 Celery、Embedding 服务或 AI Provider。

### 阶段 B：收敛服务端契约

1. 将 base/document DTO 收敛为主数据字段。
2. 保留 iOS 现有 sync push/pull 全量契约和 mutation 类型。
3. 删除 search/files/index/rerank API，保留知识库和文档的 PATCH/DELETE。
4. 移除 Chat Context 与知识库的连接。
5. 增加最小 Web 接口、越权测试和 iOS 同步兼容回归测试。

完成条件：服务端 Web 入口只暴露第 4.2 节接口，同时现有 iOS sync push/pull 行为完全兼容。

### 阶段 C：收敛 Web，冻结 iOS

1. Web 删除文件、索引和检索设置界面。
2. Web 保留知识库/文档列表、新建、读取、编辑和删除。
3. 不修改 iOS 代码、工程、数据模型、同步和 UI。
4. 使用现有 iOS 构建执行同步回归，发现冲突时只修改服务端兼容层。

完成条件：Web 完成收敛，现有 iOS 无需发版且功能不回退。

### 阶段 D：删除派生数据结构

1. 确认 Celery 中没有 knowledge 任务排队或运行。
2. 导出空正文文件文档清单并完成业务确认。
3. 备份 Chunk、IndexState、IndexVersion、RetrievalAudit。
4. 执行服务端数据库删除迁移。
5. 删除服务端和 Web 剩余运行时代码、配置、测试和旧文案。
6. 再次执行现有 iOS sync push/pull 回归，不修改 iOS。

完成条件：运行时不再引用索引、Embedding、RAG 或文件导入类型。

## 8. 验收标准

### 8.1 功能验收

- Web 可以创建知识库并读取知识库列表和详情。
- Web 可以创建纯文本文档并读取列表和正文。
- Web 可以编辑和删除知识库、知识文档；过期 revision 必须产生明确冲突。
- Web 删除生成 tombstone，并能被现有 iOS pull 同步。
- 现有 iOS 可以继续离线创建、更新、删除文档，联网后按原协议同步到服务端。
- 同一账号另一台现有 iOS 设备可以继续 pull 到文档。
- 普通文本过滤不调用模型或 Embedding。
- Web 不存在文件导入、索引、语义搜索、重建或 AI 接入入口。
- Web 对话页面不显示知识库选择器。
- 服务端 AI 工具清单不包含 `search_knowledge_bag`；iOS ToolHub 不在本项验收范围。

### 8.2 异步任务验收

- Celery 注册任务中不存在 `chat_sync.ai_tasks.knowledge_tasks.*`。
- 后台异步任务页面不显示 AI 知识库任务。
- 创建、读取和同步知识文档不依赖 Celery worker。
- 停止 Celery worker后，Web 创建/读取和 iOS push/pull 仍正常工作。
- iOS 客户端同步继续按现有本地异步网络流程运行，不修改实现。

### 8.3 数据验收

- 迁移前后的有效 KnowledgeBase 数量一致。
- 迁移前后的非空 KnowledgeDocument 主数据数量一致。
- 同一 mutation 重试不会生成重复文档。
- 不同账号不能读取彼此知识库和文档。
- 删除索引表后，知识文档正文仍可正常读取。

### 8.4 删除完整性检查

除历史迁移、历史文档和本工单外，运行时代码不得再命中：

```text
KnowledgeChunk
KnowledgeIndexState
KnowledgeIndexVersion
KnowledgeRetrievalAudit
search_knowledge_bag
KnowledgeEmbedding
index_document_task
rebuild_index_version_task
extract_document_task
KNOWLEDGE_RAG_TOOL_ENABLED
KNOWLEDGE_CHAT_SELECTOR_ENABLED
```

## 9. 测试计划

### 服务端

- 创建、列表和单条读取知识库。
- 创建、列表和单条读取文档。
- 编辑、删除知识库和知识文档。
- revision 冲突、软删除 tombstone 和账号越权校验。
- 默认知识库幂等创建。
- create sync mutation 幂等重放。
- iOS `create / update / delete / restore` mutation 保持原有成功、冲突和幂等语义。
- 文档创建不会创建 Chunk、IndexState 或 Celery task。
- 无 Celery worker时接口正常。
- 账号越权隔离。
- 已删除路由不可达。

### Web

- 知识库列表、空状态、新建和读取。
- 知识库编辑、删除及冲突提示。
- 文档列表、空状态、新建、读取、编辑和删除。
- 创建提交幂等和错误提示。
- 普通文本过滤。
- 无 files/index/settings tab，无对话知识库选择器。

### iOS 兼容回归（只测试，不改代码）

- 使用当前 iOS 代码完成本地创建、读取、更新和删除。
- 离线 mutation 恢复联网后继续自动 push。
- `create / update / delete / restore` 均能得到原契约响应。
- 多设备 pull、重复 push、账号切换隔离继续正常。
- 现有本地 Chunk、Embedding、搜索、文件导入和 AI 工具行为不因服务端删减发生回退。
- 回归失败时修改服务端兼容层，不修改 iOS。

## 10. 非目标

- 不重设计记忆功能。
- 不修改聊天 Run、聊天消息同步或聊天事件 Outbox。
- 不保留关键词以外的高级搜索。
- 不新增全文检索服务。
- 不新增文件解析服务。
- 不新增 Android 实现。
- 不修改任何 iOS 代码、CoreData、接口 DTO、UI、测试或工程配置。
- 不在本工单创建阶段修改代码、数据库或线上配置。

## 11. 完成定义

只有以下条件全部满足，工单才能关闭：

1. Web 与服务端新入口收敛为知识库/文档基础增删改查，同时完整兼容现有 iOS 客户端同步。
2. 知识库 Celery 任务、索引、Embedding、RAG 和文件解析全部删除。
3. 知识库不再进入服务端聊天上下文，也不再出现在服务端 AI 工具清单。
4. iOS 仓库没有因本工单产生任何文件改动。
5. KnowledgeBase 和 KnowledgeDocument 主数据未因迁移丢失。
6. 现有 iOS `create / update / delete / restore` mutation 不会因服务端删减失败或无限重试。
7. 文档、测试、后台任务页面和部署配置不再宣称支持已删除能力。
