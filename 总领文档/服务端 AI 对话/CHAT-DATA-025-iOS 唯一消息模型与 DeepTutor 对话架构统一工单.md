# CHAT-DATA-025 iOS 唯一消息模型与 DeepTutor 对话架构统一工单

创建日期：2026-08-25  
状态：待实现  
优先级：P0 / 数据兼容阻断  
实施范围：Spark Chat Web + SparkService `chat_sync` + 跨端契约  
数据模型基线：SparkClient `ChatMessage.swift`  
业务流程参考：DeepTutor Web/Server 1.5.9  
关联工单：`CHAT-WEB-021`、`CHAT-WEB-023`、`CHAT-AI-024`  
本次交付边界：只创建全新需求工单；不修改 Web、后端、iOS、数据库、迁移、配置或测试代码。

## 一、模块目标

本工单解决同一 Spark ChatThread 中同时存在 iOS 结构和 Web/服务端结构两套消息数据的问题。

目标不是让 Web“尽可能兼容”iOS 数据，而是建立一套唯一的跨端消息领域模型：

- 消息、Block、Block Payload、NodeRole、Anchor、父子关联、状态、revision 与排序语义以 iOS `ChatMessage.swift` 为基线。
- Web 发送消息必须创建该模型的标准实例，不再提交仅含 `content` 的 Web 专用消息结构。
- 服务端数据库只保存规范化后的唯一结构，不再原样保存任意 JSON。
- Sync Push、Sync Pull、Run Create、Run Event 和 Block projection 使用同一套 Block Wire Contract。
- DeepTutor 只作为对话业务架构、Agent Loop、流式回合和工具编排的参考，不成为第二套持久化 Message 模型。

```text
DeepTutor 业务语义
  ├── Think / Act / Tool / Observe / Respond
  ├── Run / Round / Trace / Checkpoint
  └── streaming / retry / resume
              ↓ 投影
iOS Canonical Chat Domain
  ├── ChatMessage
  ├── ChatMessageBlock
  ├── ChatMessageBlockPayload
  ├── ChatMessageBlockNodeRole
  └── ChatBlockAnchor
              ↓ 同一契约
        iOS / Web / Server Sync
```

本工单完成后，系统可以存在运行时模型和 UI ViewModel，但只能存在一套可持久化、可同步、可上传的消息领域模型。

## 二、统一消息数据模型模块结构

### 2.1 结构职责表

| 层级 | 当前职责 | 当前问题 | 目标职责 |
|---|---|---|---|
| iOS Domain | 定义 Message、Block、36 种 Payload、3 种 NodeRole | 已成为实际最完整模型，但缺少跨语言 schema 作为单一事实源 | 作为 canonical 语义基线，不改成 Web 模型 |
| Web Domain Types | 声明 Block DTO 和部分 iOS kind | 同时保留 `toolCall/toolResult`，NodeRole 使用开放 string | 由共享 schema 生成/校验，禁止自定义持久化 kind/role |
| Web Normalizer | 兼容 Swift `_0`、snake/camel、扁平 payload | 宽松兼容掩盖服务端双写结构 | 仅承担版本边界适配，不成为第二事实源 |
| Run Create API | 接收 `content/references/attachments` | `content` 是 Web 专用输入，服务端自行拼出另一种 Message | 接收 canonical `input_message` + 独立 Run options |
| Sync Serializer | `blocks` 为任意 JSON | 任意 `node_role/payload/kind` 都能进入数据库 | 显式 Block/Payload/Anchor 校验 |
| Sync Persistence | 列字段 + `payload` JSON | iOS Push 保存整块 raw JSON，Run 写入保存扁平正文 | 列只存元数据，payload 只存 tagged union 内容 |
| Sync Pull | 将 DB payload 展开后补默认字段 | 同一接口可能返回两种形状 | 始终输出唯一 canonical BlockWire |
| AI Runtime | 写 `content/toolExecution/interaction` roles | iOS NodeRole 枚举无法解码 | 只写 timeline/tool/toolPresentation |
| Run Event | 传输 Block created/delta/updated | Event 内 Block 结构与 Sync 不保证一致 | Event Block 使用同一 canonical schema |
| Web UI | 将 DTO 转成卡片 | 兼容逻辑进入领域类型 | 只建立瞬时只读 ViewModel，不反向上传 |

### 2.2 当前真实目录结构

```text
SparkClient/
└── SparkClient/Projects/Features/Chat/
    ├── Domain/ChatMessage/
    │   ├── ChatMessage.swift
    │   └── ChatMessageBlockRowSnapshot.swift
    ├── Application/
    │   └── MessageRunActor.swift
    ├── Infrastructure/
    │   └── CoreDataChatStore.swift
    └── Presentation/ChatView/Components/
        └── ChatMessageBubbleContentView.swift

SparkService/
├── chat_sync/
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── ai_api/serializers.py
│   ├── ai_services/run_service.py
│   ├── ai_services/stream_writer.py
│   ├── ai_services/tool_state_service.py
│   ├── ai_services/pending_interaction_service.py
│   └── tests/
│       ├── test_sync.py
│       └── contracts/
└── chat-web/
    ├── types/chat.ts
    ├── types/sync.ts
    ├── types/run.ts
    ├── lib/api/chat-sync-api.ts
    ├── lib/api/run-api.ts
    ├── lib/chat/block-normalizer.ts
    ├── lib/chat/message-normalizer.ts
    ├── lib/event-reducer.ts
    └── context/RunControlContext.tsx
```

### 2.3 建议新增的契约目录

```text
SparkService/chat_sync/tests/contracts/
├── schemas/
│   ├── chat_message.v2.schema.json
│   ├── chat_message_block.v2.schema.json
│   ├── chat_block_payload.v2.schema.json
│   ├── chat_block_anchor.v2.schema.json
│   └── create_run.v2.schema.json
├── canonical/
│   ├── user_text_message.json
│   ├── user_image_text_message.json
│   ├── assistant_text_message.json
│   ├── assistant_tool_presentation.json
│   ├── assistant_interrupted_message.json
│   └── all_block_kinds.json
└── legacy/
    ├── web_flat_text_block.v1.json
    └── server_tool_execution_block.v1.json

SparkService/chat_sync/
└── contracts/
    ├── message_schema.py              # 建议新增：唯一 Python 校验/规范化入口
    ├── block_payloads.py              # 建议新增：payload discriminator 规则
    └── legacy_v1_adapter.py           # 建议新增：临时只读/入站适配器
```

### 2.4 目录职责与依赖方向

```text
JSON Schema / canonical fixtures
       ↓
Server serializer + canonicalizer
       ↓
Domain persistence columns + payload union
       ↓
Sync Pull / Run Event projection
       ↓
iOS Codable / Web generated types
       ↓
iOS View state / Web TurnPresentation
```

- iOS `ChatMessage.swift` 是语义基线。
- JSON Schema 是跨语言可执行契约。
- 服务端 canonicalizer 是唯一写入门禁。
- Web normalizer 只能处理明确登记的旧版本输入，不能接受无限形状。
- Web ViewModel、DeepTutor Trace 和 Provider chunk 都不能直接写 Sync 表。

## 三、能力一：唯一 ChatMessage 模型

### 3.1 需求说明

所有平台对“消息”的定义必须一致。唯一持久化 Message 由以下字段组成：

| 字段 | 类型 | 规则 |
|---|---|---|
| `thread_id` | UUID | 必须与路由/所属 Thread 一致 |
| `role` | enum | `system/user/assistant` |
| `model_name` | string/null | user 可为空或 `user`；assistant 为实际模型快照 |
| `client_message_id` | UUID | 跨端幂等主键，生成后不可改变 |
| `server_message_id` | string/null | 服务端确认后赋值；不可被另一用户复用 |
| `delivery_state` | enum | `pending/sending/sent/failed/read` |
| `created_at` | RFC3339 | 客户端创建时间，服务端做合理范围校验 |
| `server_updated_at` | RFC3339/null | 仅服务端维护 |
| `tombstone` | boolean | 删除标记，不用空 Block 模拟删除 |
| `blocks` | Canonical Block[] | 用户可见内容唯一来源 |
| `usage_summary` | object/null | 仅 assistant；服务端生成 |

顶层 `attachments`、`reasoning_content` 等旧兼容字段不得继续作为第二份消息正文。附件属于 Block；公开思考属于 `deepThought` Block；Usage 属于 `usage_summary`。

### 3.2 基础要求与业务规则

1. `client_message_id` 在同一用户下唯一，Web/iOS 重试必须复用原 ID。
2. Message 内容必须来自 Blocks；禁止同时提交 `content` 和 Text Block 两份正文。
3. 用户消息至少包含一个有效内容 Block，或包含被允许的引用/附件 Block。
4. assistant message 由服务端 Run 创建；客户端不得上传伪造的 assistant model/usage。
5. tombstone message 不再接受正文更新，除非执行显式恢复操作。
6. Message 的 `blocks` 更新按 Block ID + revision 合并，不按数组位置覆盖。
7. `server_message_id` 和数据库内部整数 ID 是不同概念，跨端只使用公开 ID。
8. Run 对 Message 的引用必须使用稳定公开标识或明确映射，不允许 Web 猜数据库主键。

### 3.3 主流程

```text
Web Composer
  → 构建 Canonical user ChatMessage
  → 本地 optimistic state（同一对象）
  → POST Run Create v2(input_message, run_options)
  → Server schema validation
  → canonical persistence
  → 创建 assistant ChatMessage + ChatRun
  → 返回同一 user/assistant message public IDs
  → Event/Sync 增量更新同一对象
```

### 3.4 失败、重试和恢复

- 相同 `client_message_id` + 相同 hash：返回原 Message/Run。
- 相同 `client_message_id` + 不同内容：返回 409 `chat_message_idempotency_conflict`。
- Block 无效：整条消息拒绝，返回精确 `blocks[n].field`，禁止部分写入。
- Run 创建失败：已提交 Message 与 Run 必须在同一事务内回滚，或以明确 failed 状态保留，不能留下无主 pending assistant。
- Web 超时后重试使用相同 Message ID 与 Idempotency-Key。

### 3.5 验收标准

- Web 发送的消息可被当前 iOS `ChatMessage` 直接解码。
- 同一 Message 从 Run Create、Sync Pull、Event replay 获得的领域字段一致。
- 不再存在 `content` 与 Text Block 正文不一致。
- Web 重试不会产生重复 user/assistant message。

### 3.6 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat-web/types/run.ts` | `CreateRunRequestDTO.content` 迁移为 canonical `input_message` |
| `chat-web/context/RunControlContext.tsx` | Composer 先构建唯一 Message，再调用 Run API |
| `chat_sync/ai_api/serializers.py` | 新增显式 `CanonicalMessageSerializer`，校验 thread/role/blocks |
| `chat_sync/ai_services/run_service.py` | 不再自行从 `content` 拼装非标准 Block；持久化已校验 Message |
| `chat_sync/models.py` | 保留现有表，但约束字段与 canonical schema 的关系 |

## 四、能力二：唯一 ChatMessageBlock 与 Payload 模型

### 4.1 需求说明

Block 必须与 iOS `ChatMessageBlock` 一致，包含：

```json
{
  "id": "uuid",
  "kind": "text",
  "status": "ready",
  "revision": 1,
  "order_key": 1000,
  "tool_call_id": null,
  "parent_tool_call_id": null,
  "parent_block_id": null,
  "node_role": "timeline",
  "anchor": null,
  "payload": {
    "text": { "_0": "用户正文" }
  },
  "created_at": "2026-08-25T09:35:07.368741Z",
  "updated_at": "2026-08-25T09:35:07.368741Z"
}
```

第一阶段 Wire 格式按当前 iOS Codable 实际可解码格式固化，包括 associated value 的 `_0` 包装。后续若要改为更标准的 tagged union，必须先给 iOS 实现自定义 Codable 并升级协议大版本，不得只让 Web/服务端先换格式。

### 4.2 基础要求与业务规则

1. `kind` 必须与 `payload` 唯一 discriminator 一致，例如 `kind=text` 对应 `payload.text`。
2. `payload` 只能保存内容 union，不得再次包含 id、thread、message、revision 等 Block 元数据。
3. Block 顶层不得扁平出现 `text/content_type/cards` 等 Payload 字段。
4. `status` 仅允许 `pending/streaming/ready/failed`。
5. `revision` 单调递增；相同 revision 内容 hash 不同视为冲突。
6. `order_key` 决定展示顺序，数组接收顺序不能成为事实。
7. `parent_block_id` 引用同一 Message 内的 Block；跨 Message 引用必须显式禁止或定义新契约。
8. `tool_call_id`、`parent_tool_call_id`、`anchor.toolCall` 必须满足关联一致性。
9. 未知未来 kind 可以在 Sync 边界安全保留，但当前 iOS 严格解码前必须通过 capability/version 门禁；不能直接污染所有客户端 Pull。

### 4.3 Payload 类型范围

以 `ChatMessageBlockKind` 的当前 36 个 case 为准：

```text
text, deepThought, tool, imageGallery, fileAttachments, knowledgeCards,
translatedText, mapRoute, events, healthCards, pendingMemberToolCards,
toolQuestionCards, toolMemberSelectionCards, healthResourceCandidateCards,
toolConsentCards, locationPermissionCards, structuredHealthCards,
sleepVisualization, stepVisualization, energyVisualization,
nutritionReadVisualization, weatherVisualization, weatherConfigCard,
searchSummary, nutritionCards, workoutVisualization, captureCard, html,
smallTaskCard, taskCards, error, assistantStatusCard,
healthResourceReference, medicalRiskNotice, medicalDisclaimerCard,
chatGuideCard
```

`toolCall`、`toolResult` 不是 iOS Message Block kind，不能继续出现在公共 TypeScript union、Sync wire 或数据库 kind 中。它们属于 Run Event 类型或 Web 临时轨迹投影。

### 4.4 失败、重试和恢复

- kind/payload 不匹配：400 `chat_block_payload_kind_mismatch`。
- node role 非法：400 `chat_block_node_role_invalid`，不得默认接受任意字符串。
- parent/tool 引用断裂：400 或将整个 Run 标记 projection failed，不能静默展示错位。
- streaming delta revision 重复：同 hash 幂等；不同 hash 触发 replay 校正。
- 单个旧历史坏 Block：Pull v2 应通过 legacy adapter 规范化；无法修复时输出明确 `error` Block，不能让整批 Message 解码失败。

### 4.5 验收标准

- 36 种 Block fixture 均能被 Swift Codable、Python serializer 和 TypeScript validator 接受。
- 非法 `content/toolExecution/interaction` NodeRole 在写入前被拒绝或规范转换。
- 公共 schema 中不存在 `toolCall/toolResult` Block kind。
- 服务端数据库 JSON 不再重复保存 Block 元数据。

### 4.6 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `SparkClient/.../ChatMessage.swift` | 语义参考基线；补跨端 fixture round-trip 测试，不先改变模型 |
| `chat_sync/serializers.py` | 将 `ListField(JSONField)` 替换为显式 Block serializer |
| `chat_sync/views.py` | 拆分 parse/canonicalize/persist/project；禁止 `payload=dict(raw)` |
| `chat-web/types/chat.ts` | 去除公共 `toolCall/toolResult`；`node_role` 使用封闭 enum |
| `chat-web/lib/chat/block-normalizer.ts` | 只处理已登记的 legacy 版本；输出 canonical Block |
| `chat_sync/tests/contracts/schemas/*` | 固化 payload union、字段约束和跨语言 fixture |

## 五、能力三：NodeRole、Anchor 与工具关联统一

### 5.1 需求说明

iOS 只定义三种 NodeRole：

| NodeRole | 语义 | 典型内容 |
|---|---|---|
| `timeline` | 主对话时间线 | 用户正文、最终回答、公开思考、状态/免责声明 |
| `tool` | 工具调用行 | `payload.tool`、工具名称、公开参数摘要 |
| `toolPresentation` | 工具结果或交互展示 | 搜索摘要、风险提示、授权卡、选择卡、可视化 |

服务端当前出现的 `content`、`toolExecution`、`interaction` 都不是合法领域值。

### 5.2 基础要求与业务规则

映射规则：

| 当前非法/旧值 | Canonical 值 | 附加处理 |
|---|---|---|
| `content` | `timeline` | Text/deepThought/status 块 |
| `toolExecution` 的调用行 | `tool` | 转成 `payload.tool` |
| `toolExecution` 的结果 | `toolPresentation` | 转成实际业务 Payload；无专用类型时使用安全展示策略 |
| `interaction` | `toolPresentation` | 使用对应 question/selection/consent/location/config payload |

1. `kind=tool` 时 `node_role` 必须为 `tool`。
2. 具有 `parent_tool_call_id` 的富结果默认 `toolPresentation`。
3. `medicalDisclaimerCard` 等时间线卡片保持 `timeline`。
4. 工具行和结果行使用同一个 `tool_call_id` 关系族。
5. Anchor 使用 iOS `messageStart/messageEnd/beforeBlock/afterBlock/toolCall` 结构；不得混入另一种列表锚点模型。

### 5.3 主流程

```text
Agent ToolCall
  → tool Block(node_role=tool, payload.tool)
  → Tool Adapter execution
  → domain result
  → toolPresentation Block(s)
  → parent_tool_call_id/tool_call_id/anchor 关联
  → iOS/Web 按同一关系投影
```

### 5.4 失败、重试和恢复

- 工具结果先于工具调用到达：按 call ID 暂存，Replay 后归并。
- 工具失败：工具行状态更新为 failed，并追加 canonical error/status presentation；不创建 `toolResult` 自定义 kind。
- 缺失 parent block：允许通过 call ID 找回；找不到时展示降级结果并记录 contract violation。

### 5.5 验收标准

- iOS 不再出现 `Cannot initialize ChatMessageBlockNodeRole from invalid String value content`。
- Web 与 iOS 对同一工具调用形成相同的调用行/结果卡顺序。
- ToolCall、ToolResult Event 可以存在，但不会成为第二种 Message Block。

### 5.6 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat_sync/ai_services/stream_writer.py` | Text Block `node_role` 从 `content` 改为 `timeline`；payload 使用 union |
| `chat_sync/ai_services/tool_state_service.py` | `toolExecution` 投影为 canonical tool/toolPresentation |
| `chat_sync/ai_services/pending_interaction_service.py` | `interaction` 投影为具体 iOS 交互卡 Payload |
| `chat-web/lib/tools/tool-activity-reducer.ts` | Tool Event 只生成 Trace ViewModel，不生成持久化 Block kind |
| `SparkClient/.../ChatMessage.swift` | 作为 defaultNodeRole 和关联规则事实依据 |

## 六、能力四：Web 发送模型与 Run Create 统一

### 6.1 需求说明

当前 Web `CreateRunRequestDTO` 发送：

```json
{
  "client_message_id": "uuid",
  "content": "什么什么",
  "references": [],
  "attachments": [],
  "client": { "platform": "web" }
}
```

服务端据此创建 `node_role=content`、扁平 `text/content_type` Block。这条快捷路径是双模型的直接来源。

目标请求：

```json
{
  "input_message": {
    "thread_id": "uuid",
    "role": "user",
    "client_message_id": "uuid",
    "server_message_id": null,
    "delivery_state": "pending",
    "created_at": "2026-08-25T09:35:07.368741Z",
    "tombstone": false,
    "model_name": null,
    "blocks": [
      {
        "id": "uuid",
        "kind": "text",
        "status": "ready",
        "revision": 1,
        "order_key": 1000,
        "node_role": "timeline",
        "tool_call_id": null,
        "parent_tool_call_id": null,
        "parent_block_id": null,
        "anchor": null,
        "payload": { "text": { "_0": "什么什么" } },
        "created_at": "2026-08-25T09:35:07.368741Z",
        "updated_at": "2026-08-25T09:35:07.368741Z"
      }
    ]
  },
  "run_options": {
    "capability": "chat",
    "preferences_revision": 1,
    "context_parent_message_id": null,
    "context_inputs": [],
    "client": { "platform": "web", "version": "...", "device_id": "..." }
  }
}
```

`run_options` 是运行命令，不是第二套 Message。一次性知识库/健康资源选择可以作为 `context_inputs`，但用户可见附件必须同时存在于 canonical attachment Block 中。

### 6.2 基础要求与业务规则

1. path thread ID 必须等于 `input_message.thread_id`。
2. Create Run 只接受 `role=user`。
3. 服务端忽略/拒绝客户端提交的 usage、assistant role 和 server-only 字段。
4. Run 与 user/assistant message 在同一数据库事务创建。
5. 返回值包含 canonical message 摘要与 Run subscription。
6. Web optimistic message 与服务端确认消息使用相同 ID/Block ID，不做临时模型替换。
7. Web 不再额外调用 Sync Push 上传同一用户消息。

### 6.3 失败、重试和恢复

- 请求验证失败保留 Composer 草稿，不插入错误 Message。
- 网络未知结果使用相同 idempotency key 查询/重试。
- 服务端已创建 Run 时返回 replayed 结果。
- attachment 上传部分成功时先完成/回滚附件准备，再提交 Message，不提交半引用 Block。

### 6.4 验收标准

- Web 发送后，iOS 立即 Pull 可以解码并展示。
- Web optimistic、Run Event、Sync Pull 不产生三份不同 Message。
- Run 创建不再写 `node_role=content`。

### 6.5 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat-web/context/RunControlContext.tsx` | 使用 canonical message factory 构建输入 |
| `chat-web/types/run.ts` | CreateRun v2 DTO 分为 input_message/run_options |
| `chat-web/lib/api/run-api.ts` | 发 v2 请求，保留一次受控 v1 compatibility flag |
| `chat_sync/ai_api/serializers.py` | v2 明确嵌套 serializer 与 server-owned 字段规则 |
| `chat_sync/ai_services/run_service.py` | 持久化 canonical input，不再构建扁平文本块 |

## 七、能力五：DeepTutor 业务流程投影到 iOS 模型

### 7.1 需求说明

DeepTutor 的 Think/Act/CallTool/Observe/Respond 是运行时流程；iOS Message/Block 是持久化结果。两者通过投影连接，不互相替代。

### 7.2 基础要求与业务规则

| DeepTutor/Spark Runtime 事实 | Canonical Message 投影 |
|---|---|
| 用户输入 | user message + timeline Blocks |
| 公开思考摘要 | assistant `deepThought` + timeline |
| ToolCall | assistant `tool` Payload + node_role=tool |
| Tool observation | 对应富 Payload + node_role=toolPresentation |
| 最终回答 | assistant `text` + node_role=timeline |
| interrupted/failed | `assistantStatusCard` + timeline |
| Usage | assistant `usage_summary` |
| Run/Round/lease/checkpoint | 不进入 Message；保留在 Run Runtime 表/Event |

1. 原始 reasoning 不因模型统一而写入 deepThought；只能写公开摘要。
2. Event 是实时传输事实，Sync Message 是最终/可恢复投影。
3. 每个 `block.created/updated/completed` Event 内的 Block 必须使用 canonical wire。
4. 前端不能从 Event 构造一种、从 Sync 构造另一种 Block。

### 7.3 主流程

```text
Run claimed
  → Context/Agent Round
  → semantic runtime event
  → canonical Block projector
  → ChatMessageBlock persistence
  → block event (same schema)
  → Web/iOS reducers
  → platform-specific ViewModel
```

### 7.4 失败、重试和恢复

- Worker 重启从 Run/Event/Checkpoint 继续，但只更新同一 assistant Message。
- Replay 与 Sync 同时到达时按 Block ID/revision 收敛。
- projection 失败必须阻止 Run completed，并产生可恢复错误，不能写入非法 Block 后仍完成。

### 7.5 验收标准

- DeepTutor 风格多轮工具流程在 iOS 与 Web 上使用同一 Message/Block 数据展示。
- Run Event 和 Sync Pull 对相同 Block 的 canonical JSON 一致。
- runtime-only 字段不会污染 Message payload。

### 7.6 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat_sync/ai_runtime/agentic/loop.py` | 只产生运行时语义 callback，不直接定义消息 JSON |
| `chat_sync/ai_services/stream_writer.py` | 作为 text/deepThought/status canonical projector |
| `chat_sync/ai_services/tool_state_service.py` | 作为 tool/presentation canonical projector |
| `chat-web/lib/event-reducer.ts` | 消费 canonical Block，Run/Trace 保持独立状态 |
| `chat-web/lib/chat/turn-presentation.ts` | 只读 ViewModel，不可上传/持久化 |

## 八、整体业务流程

### 8.1 Web 新消息发送

```text
用户输入文字/附件
  → Web MessageFactory 创建 canonical Message/Blocks
  → 本地 optimistic 插入
  → Create Run v2
  → 服务端 schema + ownership + idempotency 校验
  → Message/Blocks/assistant shell/Run 原子落库
  → Agent Loop 按 DeepTutor 业务语义运行
  → canonical Block 持续更新
  → Event 实时推送
  → Sync Pull 多端收敛
```

### 8.2 iOS 拉取 Web 消息

```text
iOS sync/pull
  → 服务端只输出 canonical MessageWire
  → ChatMessage Codable 解码整批成功
  → CoreData 按 clientMessageID/BlockID/revision upsert
  → tool/toolPresentation 关联排序
  → ChatMessageBubbleContentView 展示
```

### 8.3 历史旧数据兼容

```text
旧 DB Block
  → offline audit 分类
  → deterministic migration
  → canonical columns + payload
  → quarantine 无法转换记录
  → Sync v2 只读 canonical row
```

运行期允许一个短期 `legacy_v1_adapter` 处理尚未迁移的数据，但只允许“读旧写新”。禁止长期双写 v1/v2，禁止数据库同时保留两种 payload shape。

## 九、状态模型

### 9.1 Message 状态

```text
pending → sending → sent → read
             └────→ failed → sending（同 ID 重试）
任意非 tombstone → tombstone（终态，除非显式恢复）
```

### 9.2 Block 状态

```text
pending → streaming → ready
    └──────────────→ failed
streaming --revision++→ streaming
```

### 9.3 数据契约迁移状态

```text
legacy_detected
  → convertible → migrated → verified
  → ambiguous   → quarantined → manual_rule → migrated
  → invalid     → quarantined + safe error projection
```

## 十、数据与持久化

### 10.1 数据库规范化目标

`ChatMessageBlock` 列保存：id、message/thread/user 外键、kind、status、revision、order_key、tool 关联、node_role、anchor、时间。

`payload` JSON 只保存：

```json
{ "text": { "_0": "..." } }
```

禁止继续保存：

```json
{
  "id": "...",
  "thread_id": "...",
  "client_message_id": "...",
  "kind": "text",
  "node_role": "timeline",
  "text": "..."
}
```

### 10.2 数据修复范围

迁移前必须只读统计：

- `node_role NOT IN ('timeline','tool','toolPresentation')`。
- payload 顶层存在 `text/content_type/tool_name` 的扁平 Block。
- payload 内重复元数据字段的 Block。
- kind 与 payload discriminator 不一致。
- tool/parent/anchor 引用断裂。
- revision/order_key 缺失或冲突。
- 空 assistant pending 且无有效 active Run 的孤儿消息。

附件中的已知坏数据至少包含：

```text
client_message_id=7233a65d-c184-4a5f-a2fd-a1c196f6dce8
block_id=c73c1efe-ae35-4dd1-beee-71178f6cbaec
node_role=content
payload shape=flat text/content_type
```

该记录只能作为定位证据；迁移必须按规则扫描全部数据，不能只修一个 ID。

### 10.3 迁移策略

1. 先发布 canonical read/write 代码与 schema gate，但不开启 v2 Web 发送。
2. 全量审计并生成转换报告，不直接修改。
3. 备份后批量迁移确定性记录，记录 before/after hash。
4. 隔离歧义记录，Sync 对其使用安全 error Block，避免整批失败。
5. Web 切换 Create Run v2，服务端停止产生 legacy Block。
6. 观察无新 legacy 写入后，关闭 v1 写入口。
7. 保留限时 v1 读 adapter，最终删除。

## 十一、错误模型

| code | HTTP | 场景 | retryable |
|---|---:|---|---:|
| `chat_message_schema_invalid` | 400 | Message 字段错误 | false |
| `chat_block_schema_invalid` | 400 | Block 字段错误 | false |
| `chat_block_payload_kind_mismatch` | 400 | kind/payload 不一致 | false |
| `chat_block_node_role_invalid` | 400 | 非三种 NodeRole | false |
| `chat_block_relation_invalid` | 400 | parent/tool/anchor 关系错误 | false |
| `chat_message_idempotency_conflict` | 409 | 同 ID 不同内容 | false |
| `chat_message_thread_mismatch` | 409 | path 与 Message thread 不一致 | false |
| `chat_message_projection_failed` | 500 | Runtime 无法投影 canonical Block | true |
| `chat_legacy_block_quarantined` | 200/诊断 | 旧坏数据安全降级 | false |
| `chat_contract_version_unsupported` | 426/400 | 客户端契约版本不支持 | false |

错误响应不得回传完整消息内容、健康 payload 或附件签名 URL。

## 十二、与其他模块的接口边界

### 12.1 本模块负责

- Message/Block/Payload/NodeRole/Anchor 的唯一跨端契约。
- Web 输入构造、服务端验证、规范化持久化和 Sync/Event 出站。
- 旧数据转换与版本兼容边界。
- 跨语言 contract fixtures。

### 12.2 本模块不负责

- Provider 选择、Prompt 内容、Agent 策略和工具业务实现。
- iOS/Web 的具体视觉样式。
- 附件上传存储、知识库检索或健康资源授权本身。
- 登录、Token、设备会话和 `bootstrap`。

### 12.3 上下游

| 上游 | 输入 | 下游 | 输出 |
|---|---|---|---|
| Web Composer / iOS Chat | canonical user Message | RunService | 持久 user/assistant Message + Run |
| Agent Loop | semantic delta/tool/result | Block projector | canonical assistant Blocks |
| Sync Store | canonical rows | iOS/Web | canonical MessageWire |
| Run Event Store | canonical Block event | Web reducer | runtime state + ViewModel |

## 十三、关键代码对应关系

| 能力 | 当前代码 | 当前状态 | 目标 |
|---|---|---|---|
| iOS Message 基线 | `SparkClient/.../ChatMessage.swift` | 已存在 | 语义事实源 |
| iOS 持久化 | `SparkClient/.../CoreDataChatStore.swift` | 已存在 | 用 fixtures 验证不破坏 |
| Web Block 类型 | `chat-web/types/chat.ts` | 部分对齐 | 由 schema 约束，移除 legacy public kinds |
| Web 拉取规范化 | `chat-web/lib/chat/block-normalizer.ts` | 宽松兼容 | 限定版本的 legacy adapter |
| Web Run 输入 | `chat-web/context/RunControlContext.tsx` | content-only | canonical MessageFactory |
| Run DTO | `chat-web/types/run.ts` | Web 专用 | Create Run v2 |
| Sync 入站 | `chat_sync/serializers.py` | 任意 JSON | 显式 nested serializers |
| Sync 持久化 | `chat_sync/views.py::_upsert_message_blocks` | raw block 入 payload | canonicalize 后分列存储 |
| Sync 出站 | `chat_sync/views.py::_block_to_payload` | 展开 payload | 组装唯一 BlockWire |
| Run 消息创建 | `chat_sync/ai_services/run_service.py` | 写 content/flat text | 使用 canonical input |
| 文本流投影 | `chat_sync/ai_services/stream_writer.py` | content + flat payload | timeline + payload.text._0 |
| 工具投影 | `chat_sync/ai_services/tool_state_service.py` | toolExecution/toolCall/toolResult | tool/toolPresentation |
| 交互投影 | `chat_sync/ai_services/pending_interaction_service.py` | interaction | iOS 对应交互 payload |

## 十四、测试策略

### 14.1 跨语言契约测试

每个 canonical fixture 必须同时通过：

1. Swift `JSONDecoder` → `ChatMessage` → `JSONEncoder` round-trip。
2. Python DRF/schema validation → persistence → projection round-trip。
3. TypeScript runtime schema validation → render projection。

不能只比较 TypeScript interface，因为 interface 在运行时不校验 JSON。

### 14.2 必测矩阵

- user 纯文本、图片+文本、文件+文本。
- assistant 流式文本、公开思考、工具行+结果卡、失败/中断。
- 36 种 Payload fixture。
- 3 种 NodeRole 和 5 种 Anchor。
- parent/tool relation、order/revision 合并。
- Run Create 幂等、超时重试、thread mismatch。
- Sync Push/Pull、Run Event replay 同结构。
- v1 flat Web Block、content/toolExecution/interaction 数据迁移。
- 单条坏 Block 不使整页 Pull 失败。
- 旧 iOS 版本拉取新 Web 消息。

### 14.3 回归门禁

- 数据库约束/serializer 测试禁止产生非法 NodeRole。
- CI 扫描 public schema 禁止加入 Web-only Block kind。
- Golden fixture hash 变化必须显式升级 contract version。
- 生产指标监控 `legacy_block_write_total`，切换后必须为 0。

## 十五、当前实现、缺口与演进

### 15.1 当前实现

- iOS 已有完整 Message、Block、Payload、NodeRole、关联和本地合并模型。
- Web 已列出 iOS Block kinds，并能解开 Swift `_0` associated value。
- 服务端已有 Message/Block 表、Sync Push/Pull、Run/Event/Block 投影。
- Block ID、revision、order_key 和工具关联字段已存在数据库列。

### 15.2 当前缺口

1. Run Create 仍以 `content` 创建 Web/Server 专用消息。
2. 服务端 Text Block 写 `node_role=content`，iOS 枚举解码失败。
3. 工具和交互写 `toolExecution/interaction`，同样不属于 iOS 模型。
4. Sync Serializer 对 Blocks 只做任意 JSON 校验。
5. Sync 入站把整个 raw Block 存入 payload，字段职责重复。
6. Sync 出站有扁平 payload 和 tagged payload 两种形状。
7. Web 公共 Block kind 仍包含 `toolCall/toolResult`。
8. 单个非法 Block 会造成 iOS 整批 Messages 解码失败。
9. 当前 contract fixtures 没有完整覆盖 iOS 36 种 Payload 和 Swift round-trip。

### 15.3 建议演进顺序

#### CHAT-DATA-025A：冻结 canonical schema

- 从 `ChatMessage.swift` 生成字段、枚举、payload 和 fixture 清单。
- 明确 `_0`、camelCase/snake_case 与字段所有权。
- Swift/Python/TypeScript 三端 contract tests 先行。

#### CHAT-DATA-025B：服务端单写模型

- 新增 canonical serializers/canonicalizer。
- Run/Stream/Tool/Interaction 全部只写 canonical rows。
- Event 与 Sync 共用 projector。
- 临时保留 v1 入站 adapter，但规范化后再落库。

#### CHAT-DATA-025C：历史数据审计与迁移

- 全量统计、dry-run、转换报告和 quarantine。
- 迁移 `content/toolExecution/interaction` 与 flat payload。
- 对已知坏线程和随机样本执行 iOS 解码验收。

#### CHAT-DATA-025D：Web Create Run v2

- Web 使用 canonical MessageFactory。
- Create Run 接收 `input_message/run_options`。
- 取消 Web content-only 写路径和 public legacy kinds。

#### CHAT-DATA-025E：关闭双模型兼容

- 观察 `legacy_block_write_total=0`。
- 关闭 v1 写入口，限时保留只读 adapter。
- 最终删除重复 normalizer 分支与旧 schema。

## 十六、整体验收标准

- [ ] 系统存在一份可执行 canonical Message/Block JSON Schema。
- [ ] 该 Schema 由当前 iOS `ChatMessage.swift` 可直接解码。
- [ ] Web 发送的是 canonical Message，不再发送正文 `content` 作为另一消息模型。
- [ ] 服务端数据库只保存 canonical Block payload，不保存 raw Block 副本。
- [ ] 服务端只写 `timeline/tool/toolPresentation` NodeRole。
- [ ] Sync Push、Pull、Run Event 的 Block JSON 一致。
- [ ] Web 公共领域类型不含 `toolCall/toolResult` Message Block。
- [ ] DeepTutor Agent Loop 的 Think/Tool/Observe/Respond 都投影到同一 iOS Message 模型。
- [ ] Run、Round、Event、Checkpoint 保持运行时模型，不污染 Message。
- [ ] 已知 `node_role=content` 数据完成迁移或安全隔离。
- [ ] 单条历史坏数据不再导致 iOS 整批 Pull 解码失败。
- [ ] 36 种 Payload 和关键关联通过 Swift/Python/TypeScript round-trip。
- [ ] 新旧 Web/iOS 同一线程能够发送、拉取、展示、重试和删除。
- [ ] 迁移期只允许“读旧写新”，没有长期双写。

## 十七、本次工单边界确认

创建本工单时：

- 未修改 Web 消息类型、发送流程或 UI。
- 未修改服务端 Serializer、RunService、StreamWriter 或数据库数据。
- 未修改 iOS `ChatMessage.swift`、CoreData 或展示流程。
- 未执行数据扫描、迁移、修复或隔离。
- 未修改 DeepTutor 源码。
- 未修改登录、Token、`bootstrap`、`api_key` 或 Run 开关配置。

