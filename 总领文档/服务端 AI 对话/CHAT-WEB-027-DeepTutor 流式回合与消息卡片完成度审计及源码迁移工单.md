# CHAT-WEB-027 DeepTutor 流式回合与消息卡片完成度审计及源码迁移工单

创建日期：2026-08-26  
状态：待实现  
优先级：P0 / Web 对话核心体验阻断  
实施范围：Spark Chat Web + SparkService `chat_sync` 服务端 AI 流式链路  
唯一消息数据模型：当前 SparkClient `ChatMessage.swift` 及其 JSON Wire Contract  
UI 与业务流程参考：DeepTutor Web/Server  
SparkService 审计基线：`22bff32917feccd56564e39cba217354eac835bc` + 2026-08-26 当前未提交工作区  
DeepTutor 参考基线：`684d615393322cd18d9edb3a85eacb3beba0d811`（`v1.5.13-7` 工作区）  
关联工单：`CHAT-WEB-023`、`CHAT-AI-024`、`CHAT-DATA-026`  
本次交付边界：只创建全新需求工单，不修改 Python、TypeScript、CSS、测试、配置、数据库、iOS 或 DeepTutor 源码。

## 一、工单结论

当前 Spark 对话不是“完全没有流式能力”，而是四个层次没有同时完成：

1. 纯文本 Provider 链路已经按真实模型 Chunk 写入 `block.delta`。
2. Agentic 最终回答仍在模型完整返回后按固定字符数切片，用户看到的是延迟后的模拟增量，不是真实 Provider 流式。
3. WebSocket、事件重放和 Reducer 已存在，但浏览器收到突发 Delta 后直接重渲染 Markdown，没有 DeepTutor 的帧级平滑显示。
4. 回合 Activity、思考轨迹和工具卡片已完成基础骨架，但历史回合、图标状态、动态计时、轨迹正文、工具详情、完成态动画及整体布局还没有完全对齐 DeepTutor。

因此，本工单不新增第二套 Session、Message、Block 或 WebSocket。目标是在现有 Spark Run/Event/Outbox/Block/iOS Contract 上补齐真实 Agentic 增量、浏览器平滑呈现和 DeepTutor 风格的回合 UI。

```text
Provider SSE / Chunk
  → Agentic Round 增量判定
  → Durable Run Event + iOS Canonical Block
  → Outbox
  → Spark Run WebSocket JSON Event
  → sequence/revision Reducer
  → TurnRenderModel（只读 UI 投影）
  → rAF 平滑显示
  → DeepTutor 风格 Activity / Trace / Answer / Tool Card
```

“字节流式更新”在本项目中的准确含义如下：

- Provider 到 SparkService：可以是 OpenAI-compatible SSE 字节流。
- SparkService 内部：标准化为 `ProviderChunk`，不能把 Provider 原始报文直接暴露给浏览器。
- SparkService 到 Web：继续使用可持久化、可排序、可重放的 WebSocket JSON 事件，不切换成第二套 SSE。
- Web 到 UI：将 `block.delta` 增量合并到 iOS Canonical Text Block，再通过 `requestAnimationFrame` 平滑揭示文本。

## 二、用户问题与期望结果

### 2.1 当前用户可见问题

1. AI 回答可能等待较长时间后一次出现，或以大段文字快速跳出，不像 DeepTutor 连续增长。
2. 工具型对话尤其明显：工具执行结束后的最终答案不是真实流式，而是服务端完成后再切片输出。
3. 回答内容虽然能显示，但活动标题、思考过程、工具轨迹和最终正文的层级仍与 DeepTutor 有差异。
4. 历史助手消息经常只有正文，没有“已完成 · 时长”的回合头和可恢复轨迹。
5. 当前 Activity 之外还可能出现额外的 `generation-status`，形成两套运行状态提示。
6. 思考轨迹按单行截断，不能像 DeepTutor 一样展示小字号、斜体、可持续增长的 Markdown 摘要。
7. 工具轨迹只有基本名称与状态，缺少 DeepTutor 的动作动词、参数 Chip、详情展开和完成态弱化。
8. 完成态仍可能使用运行中的呼吸动画，图标也没有按“思考 / 工具 / 回答完成”切换。

### 2.2 完成后的目标体验

```text
用户点击发送
  → 用户消息立即进入消息区
  → 空助手回合立即出现
  → “小鲸探索中…”开始计时并默认展开
  → 思考摘要 / 工具步骤按事件实时追加
  → 最终回答收到真实 Provider Delta
  → 浏览器以稳定帧率平滑显示 Markdown
  → 进入 final phase 后轨迹自动折叠
  → 显示“小鲸已回答 · 8s”
  → 工具结果卡按 iOS Block 类型显示
  → 刷新或断线重连后恢复相同内容和顺序
```

## 三、当前实现完成度审计

### 3.1 总体矩阵

| 能力 | 当前状态 | 代码证据 | 审计结论 |
|---|---|---|---|
| 新对话乐观用户消息 | 已实现基础 | `ThreadContext.appendOptimisticMessage()`、`RunControlContext.createRun()` | 用户消息可立即进入消息区，需补失败/重试视觉测试 |
| 空助手回合占位 | 已实现基础 | `ChatMessages.tsx` 在 active Run 无 Block 时渲染 `AssistantTurn` | 可复用，需移除重复状态条 |
| 纯文本真实 Provider 流 | 基本实现 | `run_text_loop()` → `on_chunk()` → `AsyncTextDeltaBuffer` → `StreamWriter.append_text()` | 真实增量，50ms/256 字符批量落库 |
| Agentic 最终回答真实流 | 未实现 | `run_agentic_loop()` 调用未传 `on_chunk`；`on_final_text()` 在完整结果后按 160 字符切片 | P0 根因，当前属于伪流式 |
| Agentic 工具轮 narration | 部分实现 | `on_narration_delta()` → `agent.round.delta(channel=assistant_content)` | 有事件，但没有直接形成最终正文；语义需保留 |
| Provider reasoning 分离 | 基础存在 | `ProviderChunk.reasoning_delta`、`InlineThinkFilter` | 不得直接公开隐藏推理；需建立公开摘要通道 |
| Durable Block Delta | 已实现 | `StreamWriter.append_text()` 写 Block、Event、Outbox | 保留，不另建流式表 |
| WebSocket Run 订阅 | 已实现基础 | `ChatRunConsumer`、`run.subscribe`、ticket 鉴权 | 保留，补实时延迟和重连压测 |
| Event Replay | 已实现基础 | sequence cursor、REST events、WS subscribe replay | 保留，补断线与乱序 E2E |
| Outbox 实时中继 | 已实现基础 | 每个事件 commit 后触发 relay，Beat 每分钟兜底 | 健康时实时；队列积压时可能突发，需要指标和合并策略 |
| Web Event Reducer | 已实现基础 | event ID、sequence、revision、gap buffer | 保留，增加大量 Delta 性能测试 |
| 浏览器平滑打字 | 未实现 | 当前没有 `useSmoothStreamText` 等显示层 | Delta 突发时出现跳字，需迁移 DeepTutor 纯 Hook |
| Markdown 流式稳定性 | 部分实现 | `TextBlock` 每次 Delta 重新走 `ReactMarkdown` | 缺少显示缓冲、memo、未闭合 Markdown 修复与性能门禁 |
| Turn Activity | 部分实现 | `TurnActivity.tsx`、`turn-activity-projector.ts` | 结构已接近，行为和视觉未完全一致 |
| Agent Round Trace | 部分实现 | `agent.round.*`、`turn-trace-reducer.ts` | 有 started/delta/completed/failed，但公开摘要生产不完整 |
| 工具轨迹 | 部分实现 | ToolCall/ToolResult Block + Tool Activity Reducer | 缺少 DeepTutor 详情折叠、Chip、动词和进度视觉 |
| 历史回合 Activity | 未完全实现 | 历史 `AssistantTurn` 不接收 live rounds；`TurnActivity.visible` 依赖 running/trace/thinking | 普通已完成历史回答可能不显示“已完成”头 |
| 模型思考卡 | 未对齐 | `PublicThinkingCard` 是竖线摘要；`DeepThoughtBlock` 是通用卡 | 尚未实现 DeepTutor `<details>` 交互；不能直接暴露 raw `<think>` |
| 完成态动画与图标 | 未对齐 | Activity 始终使用 `Sparkles`，label 动画未按 terminal 关闭 | 缺少 Reasoning/Tool/Responded 图标状态机 |
| 动态回合计时 | 未实现 | `duration` 只在 terminal 时计算 | 运行中没有每秒增长的 Turn Timer |
| 无障碍流式播报 | 部分实现 | 消息列表有 `aria-live=polite` | 缺 `aria-atomic=false` 的回合粒度和播报节流验证 |
| iOS 唯一消息模型 | 已建立基础 | tagged payload、`block-normalizer`、Block Registry | 必须保持，不引入 DeepTutor Message/StreamEvent 缓存模型 |

### 3.2 Agentic 伪流式根因

当前调用链：

```text
run_agentic_round()
  → Provider Chunk 持续累积到 AgenticRoundResult.text
  → 判断本轮是否有 tool_calls
  → 无工具时得到完整 final_text
  → on_final_text(final_text)
  → 按 CHAT_AI_FINAL_TEXT_CHUNK_CHARS=160 切片
  → StreamWriter.append_text()
```

问题不在 WebSocket，而在最终正文进入 `StreamWriter` 的时间太晚。即使后续每 160 字符产生事件，模型生成期间浏览器仍收不到正文。

实现真实流式时必须处理“这一轮最终会不会调用工具”的不确定性：模型可能先输出 narration，之后才出现 tool call delta。不能把工具轮 narration 提前写进最终回答 Block。

推荐方案：`DeferredFinalAnswerBuffer`。

```text
每轮 Provider text_delta
  → 暂存到 Round Buffer
  → 首个 tool_call_delta 出现
      → 将暂存文本定性为 narration
      → 写 agent.round.delta，不写 final Text Block
  → Provider 确认 finish 且全轮无 tool_call
      → 将本轮从开始起定性为 final answer
      → 以受控小批次提交 Text Block
```

为了做到“首字尽可能早”且不污染最终回答，优先顺序如下：

1. 如果 Provider 能可靠提供响应类型或 tool-call 前置标识，收到标识后立即直写最终正文。
2. 通用 OpenAI-compatible 模型无法提前确认时，允许一个很短的分类缓冲窗；缓冲只存在内存，不成为第二消息模型。
3. 一旦出现 tool call，缓冲内容只进入公开 narration 事件。
4. 无工具完成时，缓冲内容和后续内容写入同一个 iOS `payload.text._0` Block。
5. 禁止先写最终正文再因 tool call 出现而删除或回滚已公开文本。

### 3.3 Web 显示不平滑根因

当前 Web 每收到一个事件就执行：

```text
WebSocket message
  → JSON.parse
  → applyEvents
  → reduceChatEvents
  → 更新 Block payload/revision
  → ReactMarkdown 重新解析全部已生成正文
  → 浏览器重绘
```

当 Outbox、Celery 或网络把多个 Delta 聚合后送达时，文字会成段跳出；长 Markdown 还会造成频繁解析。DeepTutor 的 `useSmoothStreamText` 将“网络接收速度”和“视觉揭示速度”分离，Spark 当前缺少这一层。

目标实现：

- Reducer 继续立即接收并保存完整 Canonical Block，不能为了动画延迟事实状态。
- UI 只对当前正在流式的最后一个 Text Block使用 `requestAnimationFrame` 揭示文本。
- Run 终态、取消、错误或切换 Thread 时立即显示完整已接收文本，不保留幽灵尾部。
- `prefers-reduced-motion` 下禁用逐字效果，直接显示 Reducer 当前全文。
- 显示层状态不能写回 Sync、Block、Event 或 LocalStorage。

## 四、消息卡片对齐差距

### 4.1 目标结构

```text
AssistantTurn
├── AssistantActivity
│   ├── StreamingStatus
│   └── TraceFlow
│       ├── Public reasoning summary
│       ├── Tool call row
│       ├── Tool progress / result row
│       └── Next agent round
├── AssistantResponse
│   ├── Markdown answer
│   └── Public ModelThinkingCard（仅安全公开内容）
├── ToolPresentationSlot
├── TurnActions
└── TurnUsageSummary
```

### 4.2 当前差距清单

| DeepTutor 目标 | Spark 当前实现 | 需要补齐 |
|---|---|---|
| 运行中 Activity 展开，进入 final phase 即折叠 | 只在 Run 从 running 进入 terminal 时自动折叠 | 以 final answer phase 为切换点，不能等 Run 完成 |
| 只有存在轨迹时显示 Chevron | 即使活动体为空也可能显示 Chevron | `expandable = traceRows.length > 0` |
| 运行中动态计时，完成后冻结 | 仅完成后显示总耗时 | 增加客户端显示计时器，最终以服务端时间校正 |
| Reasoning/Tool/Responded 专用图标 | 始终使用 `Sparkles` | 迁移三个纯 SVG Mark，按 Phase 选择 |
| 完成态无呼吸动画 | label 动画没有严格按终态关闭 | 将动画类绑定 `activity.isRunning` |
| Trace 无外层厚卡，竖线挂载 | 已有基础竖线结构 | 校准间距、颜色和折叠透明度 |
| 推理行是 11px/trace Markdown、可多行 | 当前 Round 摘要是单行 ellipsis | 增加 trace Markdown variant，Chat reasoning 行不截断 |
| 工具行有动作动词和参数 Chip | 当前是名称 + 拼接字符串 | 建立脱敏 `ToolTraceViewModel`，分离 verb/chip/detail |
| 工具终态可展开详情 | 当前 TurnTraceRow 没有独立折叠详情 | 部分迁移 `TraceRowItem` 交互 |
| 最终回答帧级平滑增长 | 当前直接渲染 Reducer 全文 | 迁移 `useSmoothStreamText` |
| 完成消息避免无关重渲染 | `TextBlock` 没有 memo 边界 | 对完成回合与 Block Renderer 增加稳定 memo |
| `<think>` 有独立折叠卡 | Spark 不允许公开 raw `<think>` | 只对 canonical `deepThought` 或 public summary 使用同款壳 |
| 单一活动状态 | 还存在独立 `generation-status` | 合并到 `AssistantActivity`，避免重复状态 |
| 历史完成回合也有状态头 | 普通历史回答可能没有 Activity | 从 `turn_summary` 恢复 completed/status/duration/usage |

### 4.3 安全边界

DeepTutor `ModelThinkingCard` 的源码注释允许展示模型 raw `<think>` scratchpad，但 Spark 健康对话不得照搬该语义。

Spark 只允许展示：

- 服务端显式标记为公开的 `public_reasoning_summary`。
- iOS Canonical `deepThought` Block 中经过安全策略允许的公开摘要。
- Run 阶段、工具公开名称、脱敏参数摘要、公开结果摘要。

禁止展示：

- Provider 原始 `reasoning_delta`。
- `<think>` 原始内容、隐藏 Chain-of-Thought、系统提示词和内部 observation。
- HealthKit 原始数据、用户身份 ID、工具完整参数、内部 URL 和异常堆栈。

## 五、DeepTutor 源码迁移可行性

DeepTutor 当前参考仓库使用 Apache License 2.0。可以迁移符合许可的源文件，但必须保留版权/许可信息、记录修改，并同步更新 Spark 的第三方声明。不得把“参考实现”误写成 Spark 原创代码。

### 5.1 可直接迁移的纯源码

| DeepTutor 源文件/符号 | 迁移级别 | Spark 目标位置 | 迁移说明 |
|---|---|---|---|
| `web/hooks/useSmoothStreamText.ts` | S1 直接迁移 | `chat-web/hooks/useSmoothStreamText.ts` | 纯 React Hook，不依赖 DeepTutor 数据模型；补 reduced-motion 和测试 |
| `ReasoningMark` | S1 提取迁移 | `chat-web/components/chat/turn/marks/ReasoningMark.tsx` | 只迁移 SVG 组件和必要类型 |
| `ToolMark` | S1 提取迁移 | `chat-web/components/chat/turn/marks/ToolMark.tsx` | 不迁移工具数据结构 |
| `RespondedMark` | S1 提取迁移 | `chat-web/components/chat/turn/marks/RespondedMark.tsx` | 完成态静态图标 |
| `formatTurnDuration` 的纯格式算法 | S1 对照合并 | `chat-web/lib/chat/turn-presentation.ts` | Spark 已有实现，只补动态秒表边界，不重复建文件 |

直接迁移门禁：

1. 文件头注明来源 commit、原路径、Apache-2.0 和本地修改。
2. 更新 `chat-web/THIRD_PARTY_NOTICES.md`；当前“未包含 DeepTutor 源码”的声明必须同步调整。
3. 不携带 DeepTutor 品牌文案、i18n key、Session ID 或 StreamEvent 类型。
4. 迁移文件必须有 Spark 独立测试，不能只依赖 DeepTutor 原测试。

### 5.2 可以部分迁移的 UI 源码

| DeepTutor 模块 | 可迁移部分 | 必须重写部分 | 原因 |
|---|---|---|---|
| `AssistantResponse.tsx` | memo、`aria-live`、smooth hook 接入结构 | content 输入改为 Canonical Text Block/DisplayText，不接收 DeepTutor Message | 数据模型不同 |
| `StreamingStatus` | 布局、图标选择、呼吸动画、动态计时 | `detectStreamingMode(events)` 改为 `TurnActivityViewModel.phase` | Spark Event 是事实源 |
| `AssistantActivity` | 用户开合优先、final phase 自动折叠、CSS Grid 动画 | `StreamEvent[]` 改为 Spark `TurnRenderModel` | 禁止第二事件模型 |
| `TraceRowItem` | Row 视觉、Chevron、Chip、active/terminal 状态 | 工具名称、参数、结果改用 Spark 脱敏 Tool ViewModel | 工具协议不同 |
| `ModelThinkingCard.tsx` | `<details>` 交互、closed 自动折叠、trace Markdown 样式 | 输入必须是公开摘要，删除 raw `<think>` 语义 | 健康隐私与 CoT 边界 |
| `SimpleMarkdownRenderer` 的 `trace` variant | 字体、间距、列表和链接样式 | 使用 Spark Markdown 依赖与安全规则 | 依赖树不同 |
| `think-segments.ts` | 仅可参考流式未闭合标签算法 | 默认不迁移到生产路径 | Spark Provider 层应剥离 raw think |

### 5.3 禁止原文件整体迁移

| DeepTutor 文件 | 结论 | 原因 |
|---|---|---|
| `TracePanels.tsx`（约 2700 行） | 禁止整文件迁移 | 同时包含多业务、DeepTutor StreamEvent 和品牌逻辑，应按符号提取 |
| `UnifiedChatContext.tsx` | 禁止迁移 | 会引入第二套 Session、Message、乐观 ID 和 WS 状态机 |
| `unified-ws.ts` | 禁止迁移 | Spark 已有 ticket + Run subscribe + replay 协议 |
| DeepTutor `ChatMessages.tsx` | 禁止整文件迁移 | 消息模型和 capability 分支与 iOS Canonical Block 不同 |
| DeepTutor Server Session API | 禁止迁移 | Spark Run/Event/Outbox 已是唯一运行事实源 |
| raw `<think>` 持久化/展示逻辑 | 禁止迁移 | 违反 Spark 的公开思考与健康隐私边界 |

## 六、iOS 数据模型与前端缓存设计

### 6.1 核心原则

可以迁移 DeepTutor 的 UI 源码，但不能为了让源码运行而缓存一套 DeepTutor Message/StreamEvent 数据。缓存必须继续以 iOS 模型为主，UI 使用只读派生模型。

```text
L1 Canonical Message Cache（唯一消息事实）
  ChatMessageWireDTO / ChatBlockDTO
  key = thread_id + client_message_id/server_message_id

L2 Live Run Projection（运行时事实）
  ChatEventEnvelope + ChatRuntimeState
  key = run_id + sequence / block_id + revision

L3 Turn Render Cache（可丢弃 UI 派生）
  TurnRenderModel
  key = message_id + block_revision_fingerprint + run_last_sequence
```

约束：

- L1 可以来自 Sync API 和服务端持久化，结构必须与 iOS Wire Contract 一致。
- L2 可以断线后通过 Event Replay 重建，不能成为历史消息的第二持久化模型。
- L3 只使用 selector、`useMemo` 或轻量内存缓存；刷新后允许丢失并重新计算。
- 不把 L3 写入数据库、LocalStorage、Sync API 或 iOS Payload。
- DeepTutor UI 组件只接收 L3，不读取 Provider Chunk 或原始 Tool arguments。

### 6.2 建议新增的只读 UI 模型

```ts
interface TurnRenderModel {
  messageId: string;
  activity: {
    phase: "exploring" | "using_tools" | "composing" | "waiting" | "completed" | "failed" | "cancelled";
    label: string;
    icon: "reasoning" | "tool" | "responded";
    startedAt: string | null;
    durationMs: number | null;
    expandable: boolean;
    running: boolean;
  };
  traceRows: PublicTraceRow[];
  contentBlocks: ChatBlockDTO[];
  presentationBlocks: ChatBlockDTO[];
  usage: TurnUsageSummary | null;
}
```

该类型只是 ViewModel，不改变 `ChatMessage.swift`、JSON Payload discriminator、Block NodeRole、Anchor 或 Sync DTO。

### 6.3 历史与 Live 合并规则

1. Message 所有权以 `message_id` 为边界，禁止把当前 Run 的 Blocks 渲染到所有历史助手消息。
2. 同一个 Block ID 以更高 `revision` 覆盖低版本，不按数组位置覆盖。
3. Live Block 进入 Sync 后，使用同 ID 替换，不生成第二张卡。
4. Event Trace 只属于对应 `run_id`；完成后以 `turn_summary` 和持久化公开 Block 恢复历史展示。
5. 运行期用户手动开合属于 L3 临时 UI 状态，不写入 canonical message。

## 七、目标实现方案

### 7.1 服务端真实 Agentic 流式

需要调整的文件和方向：

| 文件 | 改动方向 |
|---|---|
| `chat_sync/ai_runtime/agentic/round_runner.py` | 将 Provider text/reasoning/tool-call delta 分通道；增加最终轮安全缓冲状态机 |
| `chat_sync/ai_runtime/agentic/loop.py` | 把每轮实时回调传到底层；明确 narration 与 finish，不在完整返回后模拟流式 |
| `chat_sync/ai_tasks/run_tasks.py` | Agentic 调用接入 `on_chunk`/final delta；删除 `on_final_text` 的 160 字符伪流式职责 |
| `chat_sync/ai_services/stream_writer.py` | 继续写同一 Text Block；支持首 Token、Delta、completed 的严格顺序和批量写入 |
| `chat_sync/ai_services/run_service.py` | 保持 durable event/outbox，不新增直接 WS 旁路 |
| `chat_sync/ai_tasks/outbox_tasks.py` | 验证高频 Delta 下顺序、延迟、积压和重试；必要时按 Run 公平调度 |

事件顺序要求：

```text
run.started
assistant.status(thinking)
agent.round.started
[agent.round.delta(public_summary / narration)]*
[tool.requested → tool.running → tool.progress → tool.completed]*
assistant.status(answering)
block.created(text, streaming)
block.delta*
block.completed
usage.final
run.completed
run.done
```

关键业务规则：

- `block.created` 必须先于第一个 `block.delta`。
- 一个助手最终回答只增长同一个 Text Block。
- `revision` 严格递增；重复、倒退 Delta 被忽略。
- Provider `reasoning_delta` 默认不写公开 Event。
- 工具轮 narration 不得混入 final Text Block。
- Run 中断时保留已确认正文，Block 标记 failed/interrupted 语义，不伪装 completed。
- 断线恢复必须从 sequence 重放出完全相同的正文。

### 7.2 WebSocket 与实时传输

保留现有 `/ws/chat/runs/`：

- Web 申请一次性 ticket。
- 连接后发送 `run.subscribe` 和 `after_sequence`。
- 服务端先加入 group，再重放 cursor 之后的 durable events。
- 实时消息和 Replay 都走相同 Event Envelope。
- Web 根据 event ID、sequence、Block revision 幂等合并。
- 4401 停止无限重连；其他异常进入指数退避和 2 秒 REST Replay fallback。

需要补充：

- 明确 `run.subscribed` 控制帧与业务 Event 的解析分支，不能用 catch 静默吞掉所有协议错误。
- 对 WebSocket 连接、订阅、首事件、最后序列、Gap、Replay 次数增加诊断指标。
- Outbox 事件从 commit 到 Web 收到的 P95 延迟必须可测。
- 同 Run 高频事件不能被其他 Run 的大量 Outbox 长时间阻塞。

### 7.3 浏览器平滑显示

建议目录：

```text
chat-web/
├── hooks/
│   └── useSmoothStreamText.ts             # S1 迁移并适配
├── components/chat/turn/
│   ├── AssistantResponse.tsx              # 建议新增，正文统一入口
│   └── marks/
│       ├── ReasoningMark.tsx
│       ├── ToolMark.tsx
│       └── RespondedMark.tsx
└── tests/
    ├── smooth-stream-text.test.tsx
    ├── assistant-response-stream.test.tsx
    └── run-stream-reconnect.test.tsx
```

显示算法：

```text
canonicalText = reducer 中完整已接收文本
shownLength   = 当前画面已经展示的字符数
backlog       = canonicalText.length - shownLength
advance/frame = clamp(ceil(backlog / 5), 2, 120)
displayText   = canonicalText.slice(0, shownLength)
```

边界规则：

- Streaming 结束：下一帧立即补齐全文。
- Regenerate 或内容缩短：立即收缩，禁止残留上一轮尾部。
- 切换 Thread：取消 rAF。
- 后台 Tab：恢复前台后按 backlog 自适应追赶，不逐字符播放数分钟。
- Reduced Motion：禁用 smoother，直接显示 canonicalText。
- 只平滑正在生成的最后一条文本，不动画历史消息和工具参数。

### 7.4 消息卡片源码迁移与适配

实施顺序：

1. 提取 DeepTutor 的三个 Mark 和 smooth Hook。
2. 建立 `TurnRenderModel`，让迁移 UI 不接触 Spark Wire 数据。
3. 将 `TurnActivity` 改为 `phase + traceRows + duration` 驱动。
4. 将 `TurnTraceRow` 拆为 reasoning row、tool row、observation row。
5. 新增 `AssistantResponse`，统一 smooth、Markdown、memo 和无障碍。
6. 将公开 `deepThought` 接入经过适配的 `ModelThinkingCard` 壳。
7. 删除独立 `generation-status`，只保留回合 Activity。
8. 历史回合从 `turn_summary` 恢复 completed、duration、usage 和权限。

## 八、阶段拆分

### W0：契约与可观测性基线

阶段目标：先证明延迟发生在哪一段，避免只调动画掩盖服务端等待。

- 固化 Event 顺序、Block revision 和 iOS Payload fixture。
- 增加 Provider Chunk、Event Commit、Outbox Publish、Web Receive、UI Paint 时间点。
- 建立纯文本和 Agentic 两套基准场景。
- 冻结 DeepTutor 来源 commit 和 Apache-2.0 声明。

出口：可以输出一轮对话的端到端瀑布时间线。

### W1：真实 Agentic 最终回答流

阶段目标：工具回合后的最终答案在 Provider 生成期间进入同一 Canonical Text Block。

- 接入 Agentic Provider Chunk callback。
- 实现 narration/final 安全分类缓冲。
- 删除完整回答后的固定字符伪切片职责。
- 验证取消、中断、空完成和工具后多轮。

出口：Agentic 第一段最终正文不等待完整模型完成。

### W2：浏览器平滑流式

阶段目标：网络事件突发时，视觉仍稳定连续。

- 迁移 `useSmoothStreamText`。
- 新建统一 `AssistantResponse`。
- 加入 memo、Markdown 未闭合场景和 reduced-motion。
- 保持 Reducer 与 canonical cache 立即完整更新。

出口：视觉增长无明显整段跳字，完成时无尾部缺失。

### W3：消息卡片完全对齐

阶段目标：Activity、Trace、Thinking、Answer 和 Tool Card 与 DeepTutor 的信息层级一致。

- 迁移 Mark。
- 补动态计时、final phase 自动折叠和 terminal 静态状态。
- 补多行 trace Markdown、工具 Chip 和详情折叠。
- 接入安全公开的 ModelThinkingCard。
- 移除重复状态条。

出口：普通文本、工具对话和历史完成回合使用同一套 Turn UI。

### W4：恢复、性能、无障碍与发布

阶段目标：在真实网络和长回答下稳定运行。

- WebSocket 断线、乱序、重复、Gap、Replay E2E。
- 10k/50k 字 Markdown 性能测试。
- 屏幕阅读器、键盘开合、Reduced Motion 验收。
- Feature Flag 灰度、监控、回滚演练。
- 更新第三方 NOTICE 和源码来源清单。

出口：通过生产门禁后默认开启。

## 九、测试与验收标准

### 9.1 服务端测试

- 纯文本 Provider 每 20ms 发一个 Delta，数据库最终正文与拼接结果完全一致。
- Agentic 最终轮每 20ms 发一个 Delta，首段 `block.delta` 在 Provider 完成前出现。
- 工具轮 narration 不进入最终回答 Block。
- tool call 在 narration 之后出现时，已缓冲内容正确进入 Round Trace。
- `block.created`、Delta revision、completed、usage、run terminal 顺序稳定。
- 取消后不再写入新 Delta。
- Worker 丢失 lease 后不继续写 Block。
- Outbox 重试不会重复 UI 文本。

### 9.2 Web 单元测试

- Reducer 忽略重复 event ID、倒退 revision 和已应用 sequence。
- 缺序事件进入 buffer，Replay 后按顺序收敛。
- Smooth Hook 能处理增长、缩短、终态补齐和 unmount。
- Reduced Motion 下直接显示完整 Reducer 文本。
- 已完成历史回合不因其他 Live 消息更新而重复解析 Markdown。
- Activity 运行中展开，进入 final phase 自动折叠，用户手动选择优先。
- terminal label 和 Mark 不再执行呼吸动画。
- 公开 reasoning 可展示，raw reasoning 不进入 DOM。

### 9.3 E2E 场景

1. 新对话纯文本：用户消息立即出现，助手逐步生成。
2. 新对话工具链：思考 → 工具 → 观察 → 最终答案真实流式。
3. WebSocket 中途断开：REST/WS Replay 后正文无重字、缺字或闪回。
4. 刷新页面：历史消息、工具卡和最终正文一致。
5. 多设备同步：Web 生成的 iOS Canonical Block 可由 iOS 正常解析。
6. 长 Markdown：标题、列表、表格、代码块在流式期间不导致页面崩溃。
7. 失败与取消：保留已生成内容并显示明确终态。

### 9.4 性能与体验指标

| 指标 | 目标 |
|---|---|
| Provider Chunk → Event Commit P95 | ≤ 100ms（含 50ms buffer） |
| Event Commit → Web Receive P95 | ≤ 250ms（健康队列） |
| Web Receive → 下一次可见 Paint P95 | ≤ 34ms |
| 事件重复导致的正文重复字符 | 0 |
| 断线 Replay 后正文差异 | 0 |
| 长回答流式期间主线程 Long Task | 单次 < 100ms，持续优化至 < 50ms |
| 完成后未显示尾部字符 | 0 |
| iOS 解码失败 | 0 |

## 十、Feature Flag 与发布方案

建议使用独立 Web/Runtime Flag，不能复用 `CHAT_AI_SERVER_RUNS_ENABLED` 作为 UI 细粒度开关：

```text
CHAT_AI_AGENTIC_TRUE_STREAM_ENABLED
NEXT_PUBLIC_CHAT_SMOOTH_STREAM_ENABLED
NEXT_PUBLIC_CHAT_DEEPTUTOR_TURN_UI_ENABLED
```

发布顺序：

1. 先部署向后兼容的服务端 Event/Block 实现。
2. 再部署 Web smoother 和新 Turn UI。
3. 先对内部账号和测试环境开启。
4. 观察首 Token、Event 延迟、Replay、前端异常和 iOS 解码指标。
5. 灰度扩大后再设为默认。

回滚规则：

- 关闭 Web smoother 只影响视觉，不影响 canonical 数据。
- 关闭新 Turn UI 回退旧渲染器，不回滚 Message/Block 数据。
- 关闭 Agentic true stream 时可暂时回到完整回答提交，但不得写第二种 Payload。
- 不通过数据库迁移、旧模型双写或修改 iOS 数据恢复。

## 十一、明确不做

- 不修改 iOS、Android、HarmonyOS 客户端内容或登录流程。
- 不修改 `bootstrap`、`api_key` 或用户模型权限逻辑。
- 不引入 DeepTutor Session API、Unified WebSocket 或 Message 模型。
- 不建立 Web 专用持久消息表。
- 不迁移历史数据，不兼容旧 Web Block 数据。
- 不公开 Provider 原始思考过程。
- 不整文件复制 `TracePanels.tsx`、`UnifiedChatContext.tsx` 或 DeepTutor `ChatMessages.tsx`。
- 本工单当前只维护需求，不执行任何代码修改。

## 十二、Definition of Done

- [ ] 普通文本和 Agentic 最终答案都是真实 Provider 增量，不是完成后切片。
- [ ] 浏览器继续使用 Spark Run WebSocket JSON Event，支持 durable replay。
- [ ] Web 视觉流通过 rAF 平滑显示，Reduced Motion 可关闭。
- [ ] Activity、Trace、Answer、Tool Card 信息层级与 DeepTutor 对齐。
- [ ] 历史与 Live 回合使用同一套 `AssistantTurn`。
- [ ] iOS Canonical Message/Block 是唯一持久化数据模型。
- [ ] DeepTutor 源码迁移只发生在批准清单内，并完成 Apache-2.0 声明。
- [ ] raw reasoning、系统提示和敏感工具参数不进入 DOM、Event 或 Sync。
- [ ] 断线重放、取消、失败、工具多轮和长回答测试通过。
- [ ] 达到本工单延迟、正确性、无障碍和跨端解码门禁。

