# CHAT-DATA-026 iOS 单一消息契约直接切换与 Web 文本降级卡修复工单

创建日期：2026-08-26  
状态：待实现  
优先级：P0 / 跨端消息展示阻断  
实施范围：Spark Chat Web + SparkService `chat_sync`  
唯一数据模型：当前 SparkClient `ChatMessage.swift`  
业务流程参考：DeepTutor Web/Server 1.5.9  
关联工单：`CHAT-DATA-025`、`CHAT-AI-024`、`CHAT-WEB-023`  
取代范围：本工单取代 `CHAT-DATA-025` 中 Web 历史数据迁移、legacy adapter、v1 双读双写和批量迁移方案；保留其“iOS 模型唯一、DeepTutor 只负责业务流程参考”的架构结论。  
本次交付边界：只创建全新需求工单；不修改 Web、后端、iOS、数据库、配置或测试代码，不执行任何数据迁移。

## 一、模块目标

本工单完成两项工作：

1. 检查 `CHAT-DATA-025` 当前实现进度，删除尚未完成切换所遗留的迁移兼容方案，直接以当前 iOS `ChatMessage.swift` 作为唯一消息契约。
2. 对比附件中的 iOS 与 Web 对话打印数据，修复 Web 将工具内容显示成“文本 / 此内容需要更新版本查看”的类型判定、Payload 读取、Anchor 和空 Block 展示问题。

本工单不迁移 Web 历史数据，不保留 Web v1 消息模型，也不批量改写历史 Block。系统只接受、写入和输出当前 iOS 模型；Web 对当前 iOS 数据直接解码与渲染。

```text
DeepTutor 业务流程
  Think → Act → Tool → Observe → Respond
                     ↓
iOS ChatMessage.swift 唯一持久化模型
  Message → Block → Payload enum → NodeRole → Anchor
                     ↓
Server 直接校验/持久化/投影
                     ↓
iOS 与 Web 按同一 Payload discriminator 解码
```

核心原则：

- `payload` 枚举 discriminator 是 Block 类型唯一事实源。
- iOS 的 `kind` 是由 `payload.kind` 计算得到，不是 Wire 必填字段。
- 数据库 `kind` 只允许作为服务端索引投影，不能覆盖 Payload 类型。
- Web 可以建立只读 UI ViewModel，但不能改变或复制 canonical Message/Block 结构。
- Run Event 是运行时事实，不是第二套 Message Block 数据。

## 二、iOS 单一消息契约直接切换模块结构

### 2.1 结构职责表

| 层级 | 当前实现 | 当前问题 | 本工单目标 |
|---|---|---|---|
| iOS Domain | `ChatMessageBlock.kind` 从 `payload.kind` 计算 | Wire JSON 不包含 `kind`，服务端却假设它存在 | 明确 Payload discriminator 为唯一类型源 |
| Sync 入站 | Block 使用任意 JSON，缺失 kind 默认 `text` | iOS tool payload 被持久化为 kind=text | 从 payload 解析 kind，禁止默认 text 掩盖错误 |
| Canonical 模块 | 已有 36 kinds、3 roles、tagged payload helper | 同时包含 legacy kind/role/payload 归一化 | 删除 legacy adapter，只做严格 canonical 校验 |
| Run Create | Web 已发送 `input_message/run_options` | 服务端仍接受 v1 `content` 并回填字段 | 删除 v1 输入，只接受 canonical input message |
| Stream/Tool 投影 | 部分已写 `_0` tagged payload | 仍存在双路径及部分结果投影不完整 | 所有写入直接输出 iOS Payload enum |
| Sync 出站 | 调用 `normalize_block(kind,row,payload)` | stale DB kind 会把 canonical tool 判为 text | 忽略 stale kind，从 payload discriminator 投影 |
| Web Decoder | 深度解开 `_0` 并保留 payload 外层 key | 又相信 `raw.kind`，Anchor 使用另一套类型 | 保留 canonical DTO，派生 kind/value ViewModel |
| Web Renderer | Registry 按 `block.kind` 分派 | tool payload 被送入 TextBlock | 按 derived kind/node role 分派 |
| 空 Block | TextBlock 无文本时显示更新版本卡 | 合法空占位被误判为版本不支持 | 空文本不渲染；仅未知 discriminator 显示升级提示 |

### 2.2 当前真实目录结构

```text
SparkClient/
└── SparkClient/Projects/Features/Chat/
    ├── Domain/ChatMessage/ChatMessage.swift
    ├── Application/MessageRunActor.swift
    ├── Infrastructure/CoreDataChatStore.swift
    └── Presentation/ChatView/Components/ChatMessageBubbleContentView.swift

SparkService/
├── chat_sync/
│   ├── contracts/
│   │   ├── __init__.py
│   │   └── canonical.py
│   ├── management/commands/
│   │   └── migrate_canonical_blocks.py
│   ├── serializers.py
│   ├── views.py
│   ├── ai_api/serializers.py
│   ├── ai_services/
│   │   ├── run_service.py
│   │   ├── stream_writer.py
│   │   ├── tool_state_service.py
│   │   └── pending_interaction_service.py
│   └── tests/
│       ├── contracts/test_canonical.py
│       ├── test_migration_command.py
│       └── test_sync.py
└── chat-web/
    ├── types/
    │   ├── chat.ts
    │   ├── run.ts
    │   └── sync.ts
    ├── context/RunControlContext.tsx
    ├── lib/chat/
    │   ├── block-normalizer.ts
    │   ├── message-normalizer.ts
    │   ├── turn-presentation.ts
    │   └── answer-text.ts
    ├── lib/tools/tool-block-normalizer.ts
    └── components/chat/
        ├── blocks/registry.tsx
        ├── blocks/TextBlocks.tsx
        ├── blocks/ToolBlocks.tsx
        └── turn/AssistantTurn.tsx
```

### 2.3 目录职责与依赖方向

```text
ChatMessage.swift Payload enum
        ↓ 生成跨端 fixtures/schema
Strict server decoder
        ↓
canonical database columns/payload
        ↓
Sync/Event canonical encoder
        ↓
Web strict decoder
        ↓
derived BlockView(kind + associatedValue)
        ↓
TurnPresentation / Renderer
```

- `canonical.py` 只实现严格 iOS contract，不负责迁移旧 Web 数据。
- `views.py` 负责 Sync 所有权、revision 和持久化，不猜测未知 payload。
- `block-normalizer.ts` 应改为严格 decoder；规范数据不能被“归一化”为另一种 DTO。
- Renderer 只读取解码后的 associated value，不在每个组件重复猜 Payload shape。

## 三、能力一：当前实现进度验收

### 3.1 需求说明

根据 2026-08-26 当前工作区源码，`CHAT-DATA-025` 已开始实现但尚未完成单模型切换。必须先确认可复用成果和需要撤销的兼容实现，避免在半切换状态继续修补。

### 3.2 当前进度矩阵

| 025 阶段/能力 | 当前状态 | 代码证据 | 结论 |
|---|---|---|---|
| 36 种 Block kind 常量 | 已实现基础 | `chat_sync/contracts/canonical.py`、`chat-web/types/chat.ts` | 保留 |
| 3 种 NodeRole 常量 | 已实现基础 | `canonical.py` | 保留并改为严格校验 |
| Tagged Payload helper | 已实现基础 | `text_payload/tool_payload/...` | 保留 |
| Web Create Run v2 | 已实现 | `RunControlContext.tsx` 已发送 `input_message/run_options` | 保留 |
| Web v2 TypeScript DTO | 已实现 | `chat-web/types/run.ts` | 收紧 kind/role/anchor 类型 |
| 服务端 v2 input_message | 部分实现 | `ChatInputMessageSerializer`、`_create_input_message_blocks` | 保留入口，删除 v1 fallback |
| StreamWriter canonical text | 已实现基础 | 使用 `NODE_ROLE_TIMELINE`、`text_payload()` | 保留 |
| ToolState canonical 写入 | 部分实现 | 已使用 tool/toolPresentation helper | 需检查每种工具专用 Payload |
| Sync canonical 出站 | 部分实现但有根因缺陷 | `_block_to_payload()` 仍把 DB kind 传给 normalize | 改为 payload-first encoder |
| Sync canonical 入站 | 未完成 | Block 仍是 `JSONField`；缺失 kind 默认 text | P0 修复 |
| Web canonical 解码 | 未完成 | 仍相信 `raw.kind`；Payload 与 renderer 形状不一致 | P0 修复 |
| Anchor 对齐 | 未完成 | Web `ChatBlockAnchor` 不是 iOS enum | P0 修复 |
| 历史迁移命令 | 已实现但不再需要 | `migrate_canonical_blocks.py` | 删除，不执行 |
| Legacy adapter | 已实现但违反新边界 | `_LEGACY_*`、`normalize_*`、v1 content path | 删除 |
| 跨语言完整 fixtures | 部分实现 | Python tests 存在，Swift round-trip 未确认 | 补严格 fixtures |

### 3.3 基础要求与业务规则

1. 已实现的 Web v2 发送和 canonical payload helper 可以复用。
2. 任何带“legacy/read-old/migrate/fallback v1”职责的代码不进入最终架构。
3. 不运行 `migrate_canonical_blocks`，不增加新数据迁移。
4. 现有 iOS 消息不是“旧数据”；它就是当前 canonical 输入，必须直接解析。
5. 进度验收以当前代码和附件实际结果为准，不能因为单测通过就判定对齐完成。

### 3.4 主流程

```text
保留：iOS enums + canonical payload builders + Web v2 request
  → 删除：v1 request + legacy maps + migration command
  → 修正：payload-first kind/anchor decoder
  → 修正：Web derived view + renderer
  → strict contract tests
```

### 3.5 失败、重试和恢复

- 删除兼容路径后收到非 canonical 请求：直接返回 400 contract error，不静默转换。
- Web 部署与服务端部署必须在同一发布窗口完成；不通过旧接口回退。
- 回滚使用整版本回滚，不在新版本内重新打开 legacy 双写。

### 3.6 验收标准

- 代码库不再包含运行中的 v1 content-only Create Run 分支。
- 不再存在可执行历史 Block 批量迁移命令。
- canonical decoder 对非法 kind/role/payload 返回错误，不默认改成 text/timeline。
- 当前 iOS 打印数据无需改写即可被 Web 正确渲染。

### 3.7 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat_sync/contracts/canonical.py` | 删除 legacy maps/normalization；重构为严格 decode/encode |
| `chat_sync/management/commands/migrate_canonical_blocks.py` | 删除文件及命令入口，不执行迁移 |
| `chat_sync/tests/test_migration_command.py` | 删除迁移测试，替换为 strict rejection 测试 |
| `chat_sync/ai_api/serializers.py` | 删除 content/client_message_id 顶层 v1 字段和回填逻辑 |
| `chat_sync/ai_services/run_service.py` | 删除 input_message 缺失时构建 text Block 的 fallback |

## 四、能力二：iOS 与 Web 打印数据差异分析

### 4.1 需求说明

两份附件对应同一线程：

```text
thread_id = c3886850-8caa-4387-a97e-f04d44653dcc
title     = 乳腺结节解读建议
messages  = system + 2 user + 2 assistant
```

Message ID、client_message_id、Block ID、order_key 和最终正文基本可以一一对应，说明问题不在消息拉取、Thread 选择或 ID 关联，而在 Block 类型与 Payload 投影。

### 4.2 差异矩阵

| 项目 | iOS 打印 | Web 打印 | 问题 |
|---|---|---|---|
| Block `kind` | 不输出；Swift 从 `payload.kind` 计算 | 所有 Block 都出现 `kind=text` | 服务端缺失默认值覆盖真实类型 |
| Tool payload | `payload.tool._0` | normalizer 后为 `payload.tool` | Web DTO 被改形，但 renderer 不读取 `payload.tool` |
| ToolPresentation | node_role 正确，但 payload 为 `text._0=""` | kind=text、payload.text="" | 空占位被 TextBlock 渲染为升级提示 |
| Anchor | `{type:"toolCall", value:"call_*"}` | 一组 `list/item_*` 空字段 | Web Anchor 模型属于另一套协议，关联语义丢失 |
| 最终文本 | `payload.text._0` | `payload.text` string | 展示正常只是当前 normalizer 的偶然结果 |
| content preview | iOS 包含工具错误/工具结果，用户预览前有空行 | Web 只显示时间线正文 | 两端 preview 选择规则不一致 |
| 空文本 Block | 多个合法空占位：order 1000/4100/6100/7001 | 同样存在 | Web 不应将空值解释为版本不支持 |
| UIContextMenu 日志 | `no context menu is visible` | 无对应数据 | UIKit 交互告警，与消息模型/降级卡无关 |

### 4.3 已确认根因

#### 根因 A：服务端把缺失 kind 默认成 text

iOS `ChatMessageBlock` 的 `kind` 是计算属性：

```swift
var kind: ChatMessageBlockKind { payload.kind }
```

Swift Codable 输出中没有独立 `kind`。当前 Sync 入站却执行等价逻辑：

```python
raw_kind = raw.get("kind", "text")
normalize_block(kind=raw_kind, payload=raw_payload)
```

因此 `payload.tool`、`payload.medicalRiskNotice`、`payload.searchSummary` 只要没有显式 kind，就会写入 `kind=text`。

#### 根因 B：canonicalizer 相信 kind，不相信 payload

当前 `normalize_block()` 先计算 `canonical_kind(kind)`；即使 `payload_kind(payload)` 已能识别 `tool`，也不会用 discriminator 改正 kind。这使“kind=text + payload.tool”被视为可输出结构。

#### 根因 C：Web Normalizer 与 Renderer 使用不同 Payload 层级

Web 将 `_0` 递归解开，但保留 discriminator：

```json
{ "tool": { "name": "...", "content": "..." } }
```

`ToolBlock` 却读取：

```text
block.payload.name
block.payload.result_preview
```

正确值实际位于 `block.payload.tool.name`。TextBlock 则刚好读取 `block.payload.text`，造成“文本看起来正常、工具全部失败”的不对称现象。

#### 根因 D：Web 以 kind=text 调用了 TextBlock fallback

工具块和空 toolPresentation Block 都被送入 `TextBlock`。提取不到非空 `payload.text` 后，组件主动返回：

```text
标题：文本
副标题：此内容需要更新版本查看
```

所以该文案不是服务端返回，也不是 iOS 内容，而是 Web `TextBlocks.tsx` 对错误类型分派和空文本的本地降级结果。

#### 根因 E：工具结果展示数据本身为空

附件中多个 `node_role=toolPresentation` Block 的 canonical Payload 是：

```json
{ "text": { "_0": "" } }
```

这些 Block 只有 parent/tool/anchor 关系，没有 `medicalRiskNotice` 或 `searchSummary` 实际内容。即使修正 kind，它们也不应生成卡片。若产品需要持久化风险提示/引用卡，工具生产端必须直接写对应 iOS Payload enum，不能用空 Text Block 代替。

### 4.4 基础要求与业务规则

1. Payload discriminator 比显式 kind、node role 和默认值优先。
2. Wire 中不要求 `kind`；如果服务端为诊断输出 kind，它必须等于 payload discriminator。
3. Web 不得深度改写 canonical DTO 后仍称其为同一数据模型。
4. 空 Text Block 是空内容，不是未知版本。
5. “此内容需要更新版本查看”只用于未知 Payload discriminator，不能用于已知类型的空值或字段读取错误。
6. UIKit context menu warning 单独记录为非阻断 UI 日志，不进入本工单修复范围。

### 4.5 验收标准

- 附件中 `payload.tool` Block 在 Web 被识别为 tool，而不是 text。
- 4100/6100/7001 等空 Text Block 不再显示升级提示。
- Anchor 在 Web 保留 `{type, value}`。
- 同一 Message 的 iOS/Web preview 规则一致。

### 4.6 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `SparkClient/.../ChatMessage.swift` | 作为 kind/payload/anchor 事实依据，不创建 Web 变体 |
| `chat_sync/views.py::_upsert_message_blocks` | kind 从 payload discriminator 解析，不默认 text |
| `chat_sync/views.py::_block_to_payload` | payload-first 输出，DB kind 仅做一致性诊断 |
| `chat-web/lib/chat/block-normalizer.ts` | 替换为严格 decoder；保留 canonical payload |
| `chat-web/types/chat.ts` | Anchor 改为 iOS `type/value` union；kind 设为 derived field |
| `chat-web/components/chat/blocks/TextBlocks.tsx` | 已知空文本返回 null，不显示升级提示 |

## 五、能力三：Payload-first 严格 Block 解码

### 5.1 需求说明

服务端和 Web 必须使用同一算法从 iOS Payload enum 得到 Block 类型与 associated value。

```text
payload object
  → 必须只有一个已知 discriminator
  → discriminator value 必须包含 _0
  → kind = discriminator
  → value = payload[kind]._0
  → 校验 kind/value/nodeRole 组合
```

### 5.2 基础要求与业务规则

1. Payload 不是 object、没有 discriminator、包含多个 discriminator 或缺 `_0`：直接 contract error。
2. 不允许 unknown kind 默认为 text。
3. 不允许 unknown node role 默认为 timeline。
4. 显式 `kind` 存在且与 discriminator 不同：服务端拒绝写入；出站记录 contract violation。
5. canonical Block DTO 保留原始 tagged Payload，Renderer 使用 selector 提取 associated value。
6. 数据库 kind 写入 discriminator 值；读取时 discriminator 仍是事实源。

### 5.3 目标服务端接口

```python
def decode_payload(payload: dict) -> DecodedPayload:
    # returns kind + associated_value, never legacy conversion

def validate_block(block: dict) -> CanonicalBlock:
    decoded = decode_payload(block["payload"])
    if block.get("kind") not in (None, decoded.kind):
        raise BlockKindMismatch()
    validate_node_role(decoded.kind, block["node_role"])
    validate_anchor(block.get("anchor"))
    return CanonicalBlock(kind=decoded.kind, payload=block["payload"], ...)
```

### 5.4 目标 Web 接口

```ts
type DecodedBlock = {
  wire: CanonicalChatMessageBlock;
  kind: ChatMessageBlockKind;
  value: unknown;
};

function decodeBlock(wire: CanonicalChatMessageBlock): DecodedBlock {
  const [kind] = knownPayloadKeys(wire.payload);
  assertSingleKindAndAssociatedValue(kind, wire.payload[kind]);
  return { wire, kind, value: wire.payload[kind]._0 };
}
```

这不是第二套消息模型；`DecodedBlock` 是只读解码结果，不可上传、不可持久化。

### 5.5 主流程

```text
iOS Sync Push / Server Runtime Block
  → strict decode payload
  → validate role/anchor/relation
  → persist canonical payload + derived index kind
  → Sync/Event encode exact payload
  → Web strict decode
  → Renderer(kind, value)
```

### 5.6 失败、重试和恢复

- 请求入站非法：400，返回 Block index 和稳定 error code。
- Runtime 生成非法 Block：Run projection failed，不发布 completed。
- Web 收到非法 Block：隔离该 Block，显示“内容格式错误”诊断卡；不显示“需要更新版本”假结论。
- 不尝试把非法字段改写成 text。

### 5.7 验收标准

- `payload.tool._0` 必然得到 kind=tool。
- `payload.text._0` 必然得到 kind=text。
- kind/payload mismatch 在 Python 和 TypeScript 测试中都失败。
- canonical Payload 在 Web 状态中不被深度改形。

### 5.8 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat_sync/contracts/canonical.py` | 用 `decode_payload/validate_block` 取代 normalize/legacy maps |
| `chat_sync/serializers.py` | Block 从 JSONField 改为 strict serializer/validator |
| `chat_sync/views.py` | 入站和出站都调用 strict contract |
| `chat-web/lib/chat/block-normalizer.ts` | 重命名/重构为 canonical decoder |
| `chat-web/types/chat.ts` | 区分 Wire Block 与只读 DecodedBlock |

## 六、能力四：Web 工具、正文与空 Block 渲染修复

### 6.1 需求说明

Web 渲染必须按 derived kind 和 NodeRole 分类，不能只按服务端顶层 kind 字符串分派。

### 6.2 基础要求与业务规则

| Block 条件 | 目标分类 | 展示 |
|---|---|---|
| kind=text + timeline + 非空 | content | Markdown 正文 |
| kind=text + 任意 role + 空 | hidden | 不渲染，不显示升级提示 |
| kind=deepThought | thinking | 公开思考卡 |
| kind=tool + node_role=tool | activity | 工具活动/详情折叠行 |
| rich kind + toolPresentation | presentation | 对应业务卡 |
| assistantStatusCard | content/status | 中断、失败状态 |
| unknown discriminator | unsupported | 才显示版本升级提示 |
| malformed known payload | contract error | 显示格式错误并上报 |

1. Canonical `tool` 必须进入 `collectToolActivityRows()`，不能只识别 Web `toolCall/toolResult`。
2. 工具名称、内容和参数从 associated value 读取：`payload.tool._0`。
3. 工具 raw 参数默认折叠并脱敏；不混入最终回答复制/朗读。
4. `ToolPresentationSlot` 过滤空 Text placeholder。
5. `TextBlock` 对空字符串直接返回 null。
6. `UnsupportedBlock` 只处理未知 discriminator；组件异常用不同错误文案。

### 6.3 工具卡投影

```text
canonical tool Block
  → decoded.value {name, content, invocation_arguments}
  → ToolActivityDTO（只读 ViewModel）
  → TurnActivity/Trace

canonical rich toolPresentation Block
  → decoded kind/value
  → registry renderer
  → ToolPresentationSlot
```

如果只有 `tool` Block 而没有非空 rich presentation，Web 显示工具活动行和最终正文，不制造一张空结果卡。

### 6.4 失败、重试和恢复

- 工具 payload 字段缺失：显示通用“工具执行记录”，记录 contract error，不转成 text。
- 某个业务卡 renderer 抛错：隔离该卡，最终正文继续展示。
- WebSocket 与 Sync 同时到达：按 Block ID/revision 合并，derived kind 每次由最新 payload 重新计算。

### 6.5 验收标准

- 当前附件两条 assistant message 不再出现“文本 / 此内容需要更新版本查看”。
- `get_health_resource_context`、`insert_health_citation_sources`、`show_medical_risk_notice` 至少显示为工具活动。
- 最终回答只显示一次，复制内容不含工具 JSON。
- 空占位 Block 不产生 DOM 卡片或无障碍噪声。

### 6.6 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat-web/lib/chat/turn-presentation.ts` | 分类依据 derived kind + node role；过滤空 text |
| `chat-web/lib/tools/tool-block-normalizer.ts` | 支持 canonical tool associated value，取消只认 internal kinds |
| `chat-web/components/chat/blocks/ToolBlocks.tsx` | 接收解码后的 tool value |
| `chat-web/components/chat/blocks/TextBlocks.tsx` | 空 text 返回 null；错误文案分层 |
| `chat-web/components/chat/turn/ToolPresentationSlot.tsx` | 不渲染空 Text placeholder |
| `chat-web/components/chat/blocks/common.tsx` | 区分 unknown-version 与 malformed-known-payload |

## 七、能力五：Anchor 与内容预览对齐

### 7.1 需求说明

附件中 iOS Anchor 为：

```json
{ "type": "toolCall", "value": "call_jrnximu66tddvyvfgyfj30u3" }
```

Web 当前输出却变成 `list/item_list/item_id/...` 全为空。该结构不是 iOS `ChatBlockAnchor`，会丢失工具卡关联。

### 7.2 基础要求与业务规则

Web Anchor 必须直接对齐以下 iOS union：

```ts
type ChatBlockAnchor =
  | { type: "messageStart" }
  | { type: "messageEnd" }
  | { type: "beforeBlock"; value: string }
  | { type: "afterBlock"; value: string }
  | { type: "toolCall"; value: string };
```

Preview 统一规则：

1. 只读取 `node_role=timeline` 的用户可见正文。
2. 跳过空 Text、deepThought、tool、toolPresentation 和 status placeholder。
3. 多个 timeline Text 用单个换行连接，不产生开头空行。
4. tool content/error JSON 不进入会话列表 preview。
5. iOS、Web、服务端标题生成都复用同一语义规则。

### 7.3 主流程

```text
Blocks ordered by order_key
  → filter timeline
  → decode payload
  → select non-empty text/approved preview kinds
  → normalize whitespace
  → truncate by grapheme-safe limit
```

### 7.4 失败、重试和恢复

- Anchor value 对应的 ToolCall 不存在：保留 Anchor，降级按 order_key 展示并记录关联错误。
- Preview 没有正文：返回空字符串或业务卡安全标题，不返回 raw tool JSON。

### 7.5 验收标准

- Web 调试数据保留 `anchor.type/value`。
- iOS 与 Web 对附件两条消息得到相同 preview。
- 用户消息 preview 不再以空换行开头。

### 7.6 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat-web/types/chat.ts` | 删除列表型 Anchor 字段，改为 iOS union |
| `chat-web/lib/chat/block-normalizer.ts` | Anchor 严格保留 type/value |
| `chat-web/lib/chat/message-normalizer.ts` | 不再生成不同 Anchor 形状 |
| `SparkClient/.../ChatMessage.swift` | Anchor/preview 语义基线 |
| `SparkClient/.../GenerateChatConversationTitleUseCase.swift` | 核验只选 timeline 正文 |

## 八、整体业务流程

### 8.1 Web 发送

```text
Composer
  → 构建 iOS canonical input_message
  → Create Run v2（唯一入口）
  → strict server validation
  → canonical Message/Block 持久化
  → Agent Loop（DeepTutor 业务语义）
  → canonical Block Event
  → Web/iOS 同一解码
```

### 8.2 iOS Sync Push

```text
iOS ChatMessage Codable JSON（无独立 kind）
  → Sync strict Block decoder
  → 从 payload discriminator 得到 kind
  → 校验 NodeRole/Anchor
  → 持久 payload 原文 + derived kind index
  → Pull/Event 原样输出 canonical payload
```

### 8.3 Web 展示

```text
Canonical BlockWire
  → decode discriminator/_0
  → derived kind/value
  → Turn classification
      tool → activity
      timeline text → answer
      rich toolPresentation → card
      empty text → hidden
  → AssistantTurn
```

## 九、状态模型

### 9.1 Contract 状态

```text
received
  → decoded
  → validated
  → persisted
  → projected

received
  → invalid_contract（终止，不做 legacy conversion）
```

### 9.2 Web Block 状态

```text
canonical-valid + non-empty → rendered
canonical-valid + empty     → hidden
canonical-unknown           → unsupported-version
canonical-malformed         → contract-error
```

### 9.3 Run 状态关系

Block contract error 是 Run projection error。若 assistant 输出无法形成 canonical Block，Run 不得进入 completed；已有有效正文可以按 `CHAT-AI-024` 规则进入 interrupted 并保留可见内容。

## 十、数据与持久化

### 10.1 不迁移原则

本工单明确：

- 不扫描、转换或批量更新 Web 历史数据。
- 不执行 `migrate_canonical_blocks`。
- 不保留 quarantine/report/before-after hash 等迁移流程。
- 不为 v1 flat payload 增加读取兼容。
- 不双写 canonical 与 legacy 字段。

### 10.2 当前 iOS 数据处理

当前附件数据本身使用 `payload.<kind>._0`、三种 NodeRole 和 iOS Anchor，属于 canonical 数据。服务端和 Web 应按其真实结构直接解码。

数据库已有 stale `kind=text` 时，出站不能信任该索引列，必须从 canonical payload discriminator 派生。这个行为属于正确读取当前 iOS 模型，不属于旧 Web 数据迁移。新写入同时把 derived kind 保存正确。

### 10.3 空 ToolPresentation

`payload.text._0=""` 是 canonical 但无用户可见内容：

- 持久层可以保留关联事实。
- Web/iOS UI 不渲染空卡。
- 新工具执行若需要结果卡，生产端必须写真实 `medicalRiskNotice/searchSummary/...` Payload。
- 不允许 Web 从工具参数永久重建并保存另一份业务卡。

## 十一、错误模型

| code | HTTP/UI | 场景 | 处理 |
|---|---|---|---|
| `chat_block_payload_invalid` | 400 | payload 非 object/无 `_0` | 拒绝写入 |
| `chat_block_payload_ambiguous` | 400 | 多个 discriminator | 拒绝写入 |
| `chat_block_kind_mismatch` | 400 | 显式 kind 与 payload 不同 | 拒绝写入 |
| `chat_block_node_role_invalid` | 400 | 非 iOS 三种角色 | 拒绝写入 |
| `chat_block_anchor_invalid` | 400 | Anchor 不属于 iOS union | 拒绝写入 |
| `chat_block_relation_invalid` | 400 | tool/parent 关系错误 | 拒绝或 Run interrupted |
| `chat_web_block_contract_error` | Web 诊断卡 | 已知 kind payload 缺字段 | 隔离该卡并上报 |
| `chat_web_block_version_unsupported` | Web 升级提示 | 真正未知 discriminator | 显示升级提示 |

空 Text 不属于错误，不记录 unsupported-version。

## 十二、与其他模块的接口边界

### 12.1 本模块负责

- iOS Message/Block/Payload/NodeRole/Anchor 的严格跨端解码。
- Web tool/text/presentation 分类和空 Block 展示。
- 移除 Web/服务端 v1 消息兼容与迁移执行路径。
- Sync/Event/Database derived kind 一致性。

### 12.2 本模块不负责

- UIKit ContextMenu 告警修复。
- 历史 Web 数据恢复或批量迁移。
- Provider、Prompt、工具业务效果和医学答案正确性。
- 登录、Token、设备会话、`bootstrap` 或 `api_key`。
- 修改 DeepTutor 数据模型。

### 12.3 上下游接口

| 上游 | 输入 | 本模块输出 | 下游 |
|---|---|---|---|
| iOS Sync | ChatMessage Codable | canonical persisted Block | Sync Pull/Web |
| Web Composer | canonical input_message | user Message + Run | Agent runtime |
| Agent Loop | semantic output | canonical assistant Block | Event/Sync |
| Sync/Event | canonical BlockWire | DecodedBlock View | Web Turn UI |

## 十三、关键代码对应关系

| 问题/能力 | 当前文件 | 当前状态 | 修复方向 |
|---|---|---|---|
| Payload kind 事实源 | `SparkClient/.../ChatMessage.swift` | 正确 | 作为唯一基线 |
| Legacy normalization | `chat_sync/contracts/canonical.py` | 存在 | 删除，改 strict decode |
| Web 历史迁移 | `migrate_canonical_blocks.py` | 存在 | 删除且不执行 |
| v1 Run input | `chat_sync/ai_api/serializers.py` | 仍接受 | 删除 content fallback |
| v1 Run persistence | `chat_sync/ai_services/run_service.py` | 仍存在 else 分支 | 删除 |
| Sync 任意 JSON | `chat_sync/serializers.py` | 未对齐 | strict Block serializer |
| kind 默认 text | `chat_sync/views.py` | 根因 | 从 payload discriminator 派生 |
| 出站 stale kind | `chat_sync/views.py::_block_to_payload` | 根因 | payload-first encode |
| Web raw kind | `chat-web/lib/chat/block-normalizer.ts` | 根因 | strict payload decoder |
| Web Anchor | `chat-web/types/chat.ts` | 协议错误 | iOS type/value union |
| Text fallback | `chat-web/components/chat/blocks/TextBlocks.tsx` | 用户可见症状 | empty→null，unknown 才升级提示 |
| Tool detection | `chat-web/lib/tools/tool-block-normalizer.ts` | 只识别 internal kinds | 识别 canonical tool |
| Tool renderer | `chat-web/components/chat/blocks/ToolBlocks.tsx` | Payload 层级错误 | 读取 decoded associated value |
| Preview | iOS/Web preview selector | 规则不一 | timeline non-empty only |

## 十四、测试策略

### 14.1 附件回归 fixtures

把附件中下列代表性 Block 脱敏后加入 fixture：

- `payload.tool._0 + node_role=tool`。
- `payload.text._0="" + node_role=toolPresentation`。
- `payload.text._0=最终回答 + node_role=timeline`。
- `anchor={type:toolCall,value:call_*}`。

预期：tool → activity；空 text → hidden；最终 text → Markdown；Anchor 不变。

### 14.2 服务端测试

- 缺失 kind 的 canonical tool payload 被持久为 kind=tool。
- 显式 kind=text + payload.tool 被拒绝。
- unknown node role 不默认 timeline。
- flat `{text:"x"}` 被拒绝，不兼容转换。
- v1 content-only Create Run 被拒绝。
- Sync Pull 的 derived kind 与 payload discriminator 一致。
- Stream/Tool/Interaction 所有产出通过 strict contract。

### 14.3 Web 测试

- 不使用 raw kind，tool discriminator 正确分派。
- canonical payload 在 DTO 中保持 `_0` 和 discriminator。
- selector 正确返回 associated value。
- 空 TextBlock 不渲染任何 UI。
- 未知 discriminator 才显示“此内容需要更新版本查看”。
- malformed known payload 显示“内容格式错误”而非版本提示。
- Anchor type/value round-trip。
- Preview 排除工具 JSON 和空文本。
- copy/read-aloud 排除 tool activity。

### 14.4 跨端测试

同一个 fixture 必须通过：

1. Swift `JSONDecoder(ChatMessage.self)`。
2. Python strict decoder/persistence/projection。
3. TypeScript runtime decoder/TurnPresentation。

不再测试 legacy 输入成功；legacy 输入必须测试为失败。

## 十五、当前实现、缺口与直接切换计划

### 15.1 当前实现

- Web 已使用 canonical `input_message/run_options` 发送文本消息。
- canonical Python 模块已列出 36 kinds、3 roles 和 tagged payload builder。
- StreamWriter 已使用 canonical timeline Text Payload。
- ToolStateService 已开始写 tool/toolPresentation。
- Web 已有 TurnPresentation、Block Registry、AssistantTurn 和工具活动 UI。

### 15.2 当前缺口

1. 服务端和 Web 都没有让 Payload discriminator 成为唯一 kind 源。
2. Sync 入站仍允许任意 JSON。
3. v1 content-only 请求和后端 fallback 仍存在。
4. legacy maps、normalizer、迁移命令和迁移测试仍存在。
5. Web Anchor 是另一套数据结构。
6. Web Payload normalizer 与各 Renderer 读取层级不一致。
7. canonical tool 未进入工具活动分类。
8. 已知空 Text 被误报为需要升级。
9. 工具结果的 rich presentation 在附件中为空，没有真实 Payload。
10. iOS/Web content preview 规则不一致。

### 15.3 实施顺序

#### CHAT-DATA-026A：冻结严格 iOS Wire Contract

- 以 `ChatMessage.swift` 的实际 Codable JSON 固定 Message、Block、Payload、NodeRole、Anchor fixtures。
- 明确 Wire 不要求独立 kind；payload discriminator 为唯一类型。
- 删除 025 文档实现中的迁移验收要求。

#### CHAT-DATA-026B：服务端直接单契约

- 删除 v1 Run 输入和 legacy normalize。
- 删除迁移命令及测试。
- Sync/Run/Event 使用 strict decoder/encoder。
- stale DB kind 只做诊断，不影响 payload-first 出站。

#### CHAT-DATA-026C：Web 严格解码与渲染

- canonical DTO 保持原形。
- derived kind/value 驱动 TurnPresentation。
- 修复 Anchor、Tool activity、空 Text 和错误文案。

#### CHAT-DATA-026D：工具专用结果 Payload

- 核验每个已启用工具是否产生 iOS 已有的专用 presentation Payload。
- 无业务结果卡时不创建空 Text presentation。
- 工具 Activity 与最终结果卡分别验收。

#### CHAT-DATA-026E：跨端验收与发布

- 使用附件线程等价 fixture 做 iOS/Web 对照。
- 同一发布窗口切换 Web 与服务端。
- 监控 contract errors；不提供 legacy 回退开关。

## 十六、整体验收标准

- [ ] 当前 iOS `ChatMessage.swift` 是唯一 Message/Block 数据模型。
- [ ] DeepTutor 只用于业务流程和 Agent Loop 参考。
- [ ] Web 不考虑、不开启、也不执行历史数据迁移。
- [ ] `migrate_canonical_blocks` 和 legacy adapter 从目标实现中去除。
- [ ] 服务端不再接受 v1 content-only Create Run。
- [ ] Payload discriminator 是服务端、Web 和 iOS 的唯一 kind 来源。
- [ ] Wire Block 不依赖独立 kind；若输出 kind，其值必须与 payload 一致。
- [ ] `payload.tool._0` 在 Web 显示为工具活动。
- [ ] 空 Text Block 不产生“文本 / 此内容需要更新版本查看”。
- [ ] 未知 Payload 与 malformed known Payload 使用不同错误文案。
- [ ] Web Anchor 保留 iOS `type/value` union。
- [ ] Tool/ToolPresentation/final text 的回合顺序与 iOS 一致。
- [ ] iOS/Web preview 都排除工具 JSON 和空文本。
- [ ] Sync、Run Event 和 Web reducer 对同一 Block 输出一致。
- [ ] Swift/Python/TypeScript 严格 contract fixtures 全部通过。
- [ ] 非 canonical 输入被拒绝，不被转换为 text/timeline。

## 十七、本次工单边界确认

创建本工单时：

- 未修改 Web TypeScript、React 或 CSS。
- 未修改服务端 Python、Serializer、RunService 或数据库。
- 未修改 iOS `ChatMessage.swift`、CoreData 或 UIKit 交互。
- 未删除现有迁移命令；本工单仅要求后续实施时删除。
- 未执行任何历史数据扫描、转换、迁移或修复。
- 未修改登录、Token、`bootstrap`、`api_key` 或 Run 开关。

