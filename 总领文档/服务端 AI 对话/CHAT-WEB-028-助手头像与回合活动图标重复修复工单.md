# CHAT-WEB-028 助手头像与回合活动图标重复修复工单

创建日期：2026-08-26  
状态：待实现  
类型：Web UI Bug / 助手回合状态表达缺失  
优先级：P1  
实施范围：Spark Chat Web 对话消息区域  
参考界面：DeepTutor `AssistantActivity`  
关联工单：`CHAT-WEB-023`、`CHAT-WEB-027`  
产品决策：已确认删除固定助手头像，使用回合 Activity 图标作为助手回合的唯一状态标识；状态文案统一为“小鲸探索中… / 正在调用工具… / 小鲸正在回答… / 已完成”，并展示本轮耗时；所有 AI 对话统一使用一条真实 Provider 流式 Agentic 管线，reasoning 与 final text 分通道实时输出，iOS Canonical 消息字段保持不变；思考区域生成和工具阶段默认展开，最终答案开始时自动折叠，用户手动选择优先；轨迹按“一个 Agent Round 一条思考 Row、一个 ToolCall 一条工具 Row”稳定分组；工具呈现采用“过程轨迹 + 有价值的业务结果卡”两层结构，并复用现有 canonical 数据模型完成关联与去重。  
本次交付边界：只创建 Bug 修复工单，不修改 TypeScript、CSS、测试、后端、数据库或客户端代码。

## 一、Bug 摘要

当前 Spark Web 在 AI 开始生成回答时，同时渲染了两套助手标识：

1. 助手消息外层左侧的固定方形星芒头像。
2. `TurnActivity` 内部表示“正在思考”的星芒状态图标。

页面还可能先出现一个悬空的固定头像，再在下方出现“状态图标 + 正在思考”，造成图标重复、上下留白过大、轨迹竖线错位和回合结构割裂。

DeepTutor 将“助手身份”和“当前执行状态”合并为一个 `AssistantActivity` 状态头，不额外显示固定头像。本工单要求 Spark 采用相同结构。

## 二、问题表现

### 2.1 当前 Spark

```text
                         用户消息

□ 固定助手头像


□ 固定助手头像   ✦ 正在思考 ⌄
                 │
```

主要问题：

- 同一助手回合出现两个或三个视觉相近的星芒标识。
- 固定头像独占一列，Activity 又从正文区域内部开始，左侧基线不一致。
- 轨迹竖线无法自然连接到真正代表运行状态的图标中心。
- AI 尚未产生正文时，空助手外壳会留下一个孤立头像。
- 用户难以判断哪个图标表示助手身份，哪个表示当前生成状态。
- Activity 状态显得像正文的附属卡片，而不是整个助手回合的入口。

### 2.2 DeepTutor 目标

```text
                         用户消息

✦ DeepTutor 探索中… · 3s ⌄
│ 思考、工具和观察轨迹

最终回答正文
```

目标特征：

- 一个回合只有一个主状态图标。
- 图标、状态文字、耗时和 Chevron 位于同一行。
- 轨迹竖线从状态图标的中心线向下延伸。
- 最终正文直接与 Activity 组成同一个助手回合。
- 没有额外头像列，不产生悬空图标。

## 三、根因分析

当前组件结构为：

```text
AssistantTurn
├── message__avatar               固定 Sparkles 图标
└── message__content
    └── message__body
        ├── TurnActivity
        │   └── turn-activity__state  第二个 Sparkles 图标
        ├── contentBlocks
        └── ToolPresentationSlot
```

根因不是图标资源本身，而是同时保留了两套 UI 语义：

- `message__avatar` 延续传统聊天气泡的“助手头像”模式。
- `TurnActivity` 使用 Agentic 对话的“回合状态标识”模式。

两种模式同时存在，导致结构重复。仅隐藏其中一个 SVG 不能彻底解决问题，因为头像列的宽度、消息 gap、正文缩进和空回合占位仍会保留。

## 四、已确认产品决策

采用 DeepTutor 的单 Activity 图标结构：

- 删除助手消息左侧固定头像。
- 不为历史助手消息保留固定头像。
- 不在最终答案出现后重新显示头像。
- 运行中由 `ReasoningMark`、`ToolMark` 或对应 Activity Mark 表示状态。
- 完成后由 `RespondedMark` 表示回合完成。
- Activity 不可见的特殊回合，正文仍与其他助手回答保持同一左边界，不回退固定头像。

该决策只改变 Web 表现层，不改变：

- iOS `ChatMessage.swift` 数据模型。
- Message、Block、Run、Event、ToolCall 数据。
- Sync API、Run API 和 WebSocket 协议。
- iOS、Android、HarmonyOS UI。

### 4.1 补充确认：回合状态头与动态耗时

当前 Spark 最终回答通常只显示正文，例如：

```text
哈哈，看来你这会儿心情超棒呀……
```

相比 DeepTutor，缺少：

- 回合状态头，例如“已完成 · 8s”。
- 运行中的阶段变化，例如“探索中”“正在调用工具”“正在回答”。
- 本轮生成耗时。
- 完成态图标和静态视觉反馈。

已确认目标文案：

```text
生成中：✦ 小鲸探索中… · 3s
工具中：◉ 正在调用工具… · 5s
回答中：✦ 小鲸正在回答… · 7s
完成后：✦ 已完成 · 8s
失败时：! 生成失败 · 8s
取消时：○ 已停止 · 3s
```

文案规则：

- 运行阶段使用“小鲸”品牌名称，明确是谁正在处理。
- 完成态使用简洁的“已完成”，避免每条历史消息重复品牌名称。
- 状态和耗时之间使用视觉分隔符 `·`。
- 运行期间耗时每秒增长；完成、失败、取消后冻结。
- 不显示无法验证的历史耗时；服务端没有可靠时间时只显示终态文案。

#### 问题原因

当前状态表达存在四个断点：

1. `turn-activity-projector.ts` 已能投影部分 Phase，但公开文案仍可能混用“正在思考”“运行中”“正在处理”和“已回答”。
2. `TurnActivity.tsx` 只在终态读取格式化耗时，运行中没有每秒更新的显示计时器。
3. 历史消息依赖 `turn_summary`；缺少或没有消费 `duration_ms` 时，完成后的 Activity 可能完全不可见。
4. `ChatMessages.tsx` 仍可能额外渲染 `generation-status`，造成 Activity 状态头和底部状态条重复。

根因是 Run 状态、Assistant 阶段、显示文案和计时分别由不同组件临时判断，没有形成唯一的 `TurnActivityViewModel` 展示契约。

#### 修复方向

建立唯一状态投影：

```text
Run status + assistant.status + active tools + text streaming
  → TurnActivityViewModel.phase
  → publicStatusLabel + icon + running + duration
  → TurnActivity
```

状态优先级：

```text
failed/cancelled/interrupted
  > waiting_for_user/client_tool
  > active tool
  > final text streaming
  > exploring/thinking
  > completed
```

具体落地：

| 文件 | 修复方向 |
|---|---|
| `chat-web/lib/chat/turn-activity-projector.ts` | 集中维护 Phase、状态优先级和公开文案；禁止组件自行拼接另一套状态 |
| `chat-web/components/chat/turn/TurnActivity.tsx` | 增加运行中动态计时，按 Phase 选择 Mark，终态冻结并关闭动画 |
| `chat-web/components/chat/turn/AssistantTurn.tsx` | 传入 Run started/finished 时间及历史 `turn_summary.duration_ms` |
| `chat-web/components/chat/home/ChatMessages.tsx` | 删除重复的 `generation-status`，历史和 Live 都使用 Activity 状态头 |
| `chat-web/context/RunControlContext.tsx` | 保证 `run.started`、`assistant.status`、`run.done` 及时进入 UI 投影，不在 Context 内写显示文案 |
| `chat-web/app/globals.css` | 耗时使用 12px tabular numbers；运行态呼吸，完成态静态弱化 |
| `chat_sync/views.py` / Sync DTO | 只核验 `turn_summary.duration_ms` 是否稳定输出；缺失时补契约，不新增 Web 专用字段 |

计时事实源：

- Live Run：以服务端 `started_at` 为开始时间，浏览器时钟只负责刷新显示。
- Completed Run：优先使用 `turn_summary.duration_ms`，其次使用 `finished_at - started_at`。
- 浏览器计算值不能写回 Message、Block 或数据库。
- 服务端时间与浏览器时间存在偏差时，以服务端终态耗时覆盖 Live 显示。

#### 为什么需要记录这个问题

状态头是思考摘要、工具轨迹、折叠结构和最终答案之间的统一入口。如果状态命名和计时规则不先固定，后续会继续出现：

- Activity 显示“正在思考”，底部又显示“运行中”。
- 工具已经运行但状态仍停留在“探索中”。
- 最终答案已出现，Activity 仍保持呼吸动画。
- Live 回合有状态，刷新后历史消息状态消失。
- 同一状态在不同组件中出现不同中文名称。

因此，本问题与“删除固定头像”需要在同一工单落地：固定头像删除后，Activity 状态头将成为助手回合唯一视觉入口，必须同时具备稳定文案、图标和耗时。

### 4.2 补充确认：单一真实流式管线与思考内容

#### 已确认目标

Spark 不再保留“普通文本执行”和“Agentic 工具执行”两条 AI 回复路径。所有真实模型对话统一进入同一个 Agentic Stream Pipeline：

```text
Unified Agentic Stream Pipeline
  ├── tools=[]       普通对话
  └── tools=[...]    可调用工具的对话

ProviderChunk
  ├── reasoning_delta
  │   → 独立 reasoning 流式事件
  │   → canonical deepThought Block / Run Trace
  │   → 可折叠思考区域
  ├── text_delta
  │   → canonical text Block
  │   → 最终回答区域
  ├── tool_call_delta
  │   → ToolCall / ToolResult / Trace
  └── usage
      → Usage Event / Summary
```

“真实字节流式”在 Spark 内的定义：

```text
Provider SSE 字节流
  → ProviderChunk
  → 20–50ms 有界合并
  → Durable Run Event + Canonical Block revision
  → Outbox
  → Run WebSocket JSON Event
  → Web Reducer
  → requestAnimationFrame 平滑显示
```

浏览器仍使用 Spark 可重放的 WebSocket JSON Event，不新增第二套浏览器 SSE；“字节流”指 Provider 返回期间持续产生和消费 Delta，不能等完整答案结束后再人工切片。

#### 当前问题原因

当前执行存在两套行为：

```text
普通文本：run_text_loop → on_chunk → AsyncTextDeltaBuffer → append_text

工具对话：run_agentic_loop
  → AgenticRoundResult 累积完整 final_text
  → on_final_text(final_text)
  → 按固定字符数切片
  → append_text
```

因此会出现：

- 普通文本可能是真实流式，工具对话却等待完整回答。
- 同一模型因工具开关不同呈现不同回复体验。
- 完整答案生成后再切片只产生“视觉上的多段更新”，不是真实生成过程。
- 两条分支分别维护超时、取消、Usage、Reasoning 和错误处理，容易产生行为漂移。
- Web 无法仅根据 Event 判断当前收到的是 Provider 实时 Delta 还是完成后伪切片。

#### 单路径修复方案

所有对话统一调用：

```text
run_agentic_loop(
  tools = resolvedToolSchemas,  // 普通对话为空数组
  on_reasoning_delta,
  on_final_text_delta,
  on_tool_call_delta,
  on_usage,
  on_round,
)
```

核心要求：

1. 删除独立 `run_text_loop()` 生产执行路径；纯文本只是 `tools=[]` 的 Agentic 回合。
2. 删除完整 final text 返回后再按字符切片的伪流式职责。
3. `CHAT_AI_AGENTIC_TOOLS_ENABLED` 只决定是否向模型提供工具，不再决定 AI 执行路径。
4. 删除 `CHAT_AI_FINAL_TEXT_CHUNK_CHARS` 等只服务于伪流式切片的配置。
5. 保留 Provider/Mock、超时、最大轮次、最大工具数等真实运行控制配置。
6. reasoning、final text、tool call 和 Usage 都从同一 `ProviderChunk` 分类。

#### 工具轮与最终回答的分类问题

OpenAI-compatible 模型可能先输出一段文本，之后才发出 `tool_call_delta`。若立即把前面的文字写入最终 Text Block，后续发现是工具 narration 时将污染最终回答。

统一管线必须提供 `DeferredRoundTextClassifier`：

```text
本轮 text_delta
  → 暂存短缓冲
  → 出现 tool_call_delta
      → 缓冲内容归类为 narration
      → 写 agent.round.delta
  → 本轮完成且没有 tool call
      → 缓冲内容归类为 final answer
      → 写 canonical text Block
```

禁止先把文本公开为最终回答，再删除或回滚已推送字符。

#### reasoning 与最终回答的数据模型

现有 iOS 字段保持不变，不新增第二套 Message 或 Block：

```text
reasoning 持久化事实源
  payload.deep_thought._0.reasoning_content
  payload.deep_thought._0.reasoning_duration_ms
  payload.deep_thought._0.reasoning_expanded
  payload.deep_thought._0.reasoning_visibility

最终回答持久化事实源
  payload.text._0
```

共同使用现有字段：

- Block ID。
- `status=streaming/ready/failed`。
- 单调递增的 `revision`。
- `order_key`。
- `node_role=timeline`。
- Message、Anchor 和 ToolCall 关联。

Run Event 只负责实时传输和重放，不是第二套消息模型。新对话不得同时把 Message 级 `reasoning_content` 和 `deepThought` Block 当作两个写入事实源；统一以 `deepThought` Block 持久化思考内容，Message 级兼容字段保留但不作为新写入路径。

#### reasoning 安全过滤

已确认可以展示模型提供的 reasoning，但必须在写入公开 Event 和 `deepThought` Block 前执行基础过滤：

- 不显示 system prompt 或 developer prompt。
- 不显示密钥、Token、内部 URL 和内部服务标识。
- 不显示工具原始参数和未经脱敏的 observation。
- 不显示未经脱敏的 HealthKit、健康档案和成员身份数据。
- reasoning 与最终回答分开存储、传输和渲染。
- 模型没有 reasoning 时只显示“正在思考”，不生成或编造思考内容。
- 过滤器无法确定内容是否安全时，不公开该 reasoning Delta，但不能阻断最终回答。

#### 涉及文件与落地方向

| 文件 | 修复方向 |
|---|---|
| `chat_sync/ai_runtime/agentic/round_runner.py` | 建立统一 ProviderChunk 分类器，分离 reasoning/text/tool/usage；实现 Round Text 延迟定性 |
| `chat_sync/ai_runtime/agentic/loop.py` | 所有对话统一进入 Agent Loop；增加 reasoning/final text Delta callback；删除完整文本后回调的主职责 |
| `chat_sync/ai_tasks/run_tasks.py` | 合并普通文本和工具分支；注册同一组 StreamWriter 回调；删除固定字符伪切片 |
| `chat_sync/ai_runtime/agentic/think_filter.py` | 处理 `<think>` 与 reasoning 字段，执行安全过滤，禁止思考内容混入最终正文 |
| `chat_sync/ai_services/stream_writer.py` | 分别增量更新同一 deepThought Block 和同一 text Block，维护 created/delta/completed 顺序 |
| `chat_sync/ai_services/run_service.py` | 保持 durable Event/Outbox/sequence，不增加直接 WebSocket 旁路 |
| `SparkService/settings.py` | 删除伪流式字符切片配置；工具开关只控制 Tool Manifest，不控制执行路径 |
| `chat-web/lib/event-reducer.ts` | 独立合并 reasoning 和 text revision；断线重放不得重字、缺字 |
| `chat-web/lib/chat/turn-trace-reducer.ts` | 将 reasoning Event 投影为可折叠思考轨迹，不与最终答案合并 |
| `chat-web/components/chat/turn/PublicThinkingCard.tsx` | 消费 canonical deepThought/public reasoning，支持流式与终态折叠 |
| `chat-web/components/chat/blocks/TextBlocks.tsx` | text Block 只渲染最终回答，禁止读取 reasoning 作为正文 fallback |
| `chat-web/hooks/useSmoothStreamText.ts` | 对当前流式 reasoning/answer 使用帧级平滑显示；终态立即补齐 |

#### 流式正确性与性能约束

- `block.created` 必须先于该 Block 的第一个 Delta。
- reasoning Block 和 text Block 各自只有一个增长实例，不按 Chunk 创建新 Block。
- Event ID、sequence 和 Block revision 必须单调、可重放、幂等。
- Provider Delta 不要求逐字符落库；允许 20–50ms 或最大字符数的有界合并。
- Web 视觉可以逐帧揭示，但 Reducer 必须立即保留已经收到的完整 canonical 内容。
- 取消、超时或 lease 丢失后停止写入；已确认正文保留并显示中断状态。
- Outbox 积压恢复后不能造成重复正文。
- Markdown 渲染需要 memo 和平滑层，避免每个微小 Chunk 重新解析全部历史消息。

#### 为什么必须统一成一条路径

单一路径不是为了减少文件数量，而是确保以下行为在所有对话中一致：

- 第一段可见内容的时机。
- reasoning 与 final text 的边界。
- 工具调用前后 narration 的归属。
- 取消、超时、重试和 lease 规则。
- Usage 与模型调用次数统计。
- Event 顺序、Replay 和跨端最终数据。

如果继续保留两条执行路径，即使 Web UI 做到相同，普通对话和工具对话仍会在首 Token、错误、耗时和 reasoning 上表现不同。

### 4.3 补充确认：思考区域自动展开与折叠

#### 已确认规则

思考区域的开合行为完全对齐 DeepTutor：

```text
Run 开始 / reasoning 开始
  → 默认展开

Reasoning 流式 / Agent Round 运行
  → 保持展开并实时追加

工具请求 / 工具运行 / 工具观察
  → 保持展开并显示轨迹

首个最终答案 text_delta 到达
  → 自动折叠

Run completed
  → 默认保持折叠

Run failed / interrupted / cancelled
  → 默认展开，保留已执行轨迹和错误状态

用户手动展开或折叠
  → 本条消息生命周期内用户选择优先
  → 后续自动状态切换不得覆盖

历史完成消息
  → 默认折叠，可手动展开
```

#### 自动折叠触发点

不能等 `run.completed` 才折叠。DeepTutor 的交互重点是“思考结束，正式回答开始”时立即让出阅读空间，因此 Spark 使用首个已确认最终回答 Delta 作为触发点：

```text
assistant.status(answering)
  + canonical text Block 首个有效 text_delta
  → phase=composing
  → Activity Trace 自动折叠
```

只收到 `assistant.status(answering)` 但尚未收到正文时，不应提前折叠，避免状态误报造成空白等待。

工具轮 narration 的 `agent.round.delta(channel=assistant_content)` 不属于最终回答，不能触发折叠。只有经过 `DeferredRoundTextClassifier` 确认并写入 canonical Text Block 的 Delta 才能触发。

#### 用户操作优先级

每个助手回合保存一个仅存在于 Web 内存的开合覆盖值：

```text
userOpen = null   跟随自动阶段
userOpen = true   用户固定展开
userOpen = false  用户固定折叠
```

计算规则：

```text
expanded = userOpen ?? autoExpandedByPhase
```

约束：

- 用户第一次点击后，本条消息不再被 final phase 或 terminal phase强制开合。
- 切换 Thread、刷新页面或重新加载历史时，不持久化该临时选择。
- Regenerate 产生新 Run/新助手回合时，使用新的默认开合状态。
- 不把开合状态写入 Message、Block、Run、LocalStorage 或 iOS 数据模型。
- `deepThought.reasoning_expanded` 只作为 canonical 内容自身的默认展示建议时使用，不覆盖本轮用户已经执行的手动选择。

#### 失败与中断规则

失败、中断和取消默认展开，原因是用户需要看到系统执行到哪个阶段：

- 已完成的公开 reasoning 保留。
- 已开始或失败的工具轨迹保留。
- 不显示内部异常堆栈或敏感工具结果。
- 错误 Row 显示安全错误摘要和是否可重试。
- 用户仍可手动折叠。

如果失败发生在最终答案已经开始之后，也默认展开 Activity，但不得删除已经生成的最终正文。

#### 涉及文件与修复方向

| 文件 | 修复方向 |
|---|---|
| `chat-web/components/chat/turn/TurnActivity.tsx` | 实现 `userOpen: boolean | null`、自动 Phase 开合、用户操作优先和 Grid 折叠动画 |
| `chat-web/lib/chat/turn-activity-projector.ts` | 输出 `autoExpanded`、`isFinalAnswerPhase`、`isTerminal`、`hasTrace` 等稳定 ViewModel，不在组件猜状态 |
| `chat-web/components/chat/turn/AssistantTurn.tsx` | 将 text Block 首 Delta、Run 状态、Trace 与 thinking Block 组合为同一回合 Phase |
| `chat-web/lib/event-reducer.ts` | 保持 reasoning/text Event 顺序，首个 canonical text Delta 可被可靠识别 |
| `chat-web/lib/chat/turn-trace-reducer.ts` | narration 不得误标为 final answer；失败轨迹保持可恢复 |
| `chat-web/context/RunControlContext.tsx` | Replay 后恢复相同 Phase；不得把用户开合状态放入运行时事实层 |
| `chat-web/app/globals.css` | 使用 `grid-template-rows` 和 opacity 过渡；支持 `prefers-reduced-motion` |

#### 为什么采用这套规则

- 运行中展开，让用户确认 AI 确实在工作，而不是页面卡死。
- 工具期间展开，让用户看到搜索、读取、授权和观察进度。
- 最终答案开始即折叠，把阅读焦点交还给正式回答。
- 用户操作优先，避免正在阅读思考内容时被系统突然关闭。
- 历史默认折叠，避免长 reasoning 挤占对话阅读空间。
- 失败默认展开，帮助用户理解停止在哪个公开阶段。

#### 开合验收场景

1. 只有 reasoning、尚无正文：展开。
2. reasoning 持续追加：保持展开且不抖动。
3. 工具开始和结束：保持展开。
4. narration 出现：保持展开。
5. 首个最终 Text Block Delta：自动折叠一次。
6. 用户在生成中手动折叠：后续工具和正文不得自动展开。
7. 用户手动展开后最终正文开始：不得自动折叠。
8. Run 完成后刷新：历史默认折叠。
9. Run 失败或中断：默认展开。
10. Reduced Motion：立即切换开合，不播放高度与透明度动画。

### 4.4 补充确认：Agent Round 与 ToolCall 轨迹分组

#### 已确认规则

Reasoning 和工具过程完全对齐 DeepTutor 的可读轨迹结构，按稳定业务实体分组，不按 Provider Delta 创建 UI 行：

```text
✦ 小鲸探索中… · 5s
│
├─ 模型思考
│  正在分析用户的问题……
│
├─ 搜索健康资料   “睡眠改善”
│  已找到 6 条参考内容
│
├─ 模型思考
│  正在根据资料组织建议……
│
└─ 开始生成最终回答
```

分组规则：

- 一个 `round_id` 对应一条模型思考 Row。
- 同一 `round_id` 的 reasoning Delta 持续追加到该 Row，不创建新 Row。
- 一个 `tool_call_id` 对应一条工具 Row。
- requested、running、progress、completed、failed、cancelled 更新同一 Tool Row。
- 一个 Agent Round 可以包含多个 ToolCall，按 `call_index` 稳定排列。
- 工具执行结束并进入下一次模型调用时，创建新的 Round Row。
- 最终回答不作为 Trace Row，进入独立 canonical Text Block 和正文区域。
- Usage 不作为 Trace Row，显示在回合底部 Usage Summary。

#### 稳定标识与归属

```text
Run
├── round_id=0
│   ├── reasoning row
│   ├── tool_call_id=call_a
│   └── tool_call_id=call_b
├── round_id=1
│   ├── reasoning row
│   └── tool_call_id=call_c
└── round_id=2
    └── final answer（不进入 Trace）
```

服务端必须为每个事件提供：

| 事件 | 必需关联字段 |
|---|---|
| `agent.round.started/delta/completed/failed` | `run_id`、`round_id`、`index`、`sequence` |
| `tool.requested/running/progress/completed/failed/cancelled` | `run_id`、`round_id` 或 `round_index`、`tool_call_id`、`call_index`、`sequence` |
| reasoning Delta | `round_id`、`channel=reasoning_content`、`text_delta` |
| narration Delta | `round_id`、`channel=assistant_content`、`text_delta` |

`round_id` 和 `tool_call_id` 在 Run 生命周期内必须稳定。Web 不得使用数组下标、显示名称或事件序号代替实体 ID。

#### Reasoning Row

同一 Round 的 Reasoning Row 是持续增长的单一投影：

```text
agent.round.started
  → 创建 running Round Row

agent.round.delta(reasoning_content)
  → 追加到现有 Row.publicReasoning

agent.round.completed
  → Row.status=completed

agent.round.failed
  → Row.status=failed
```

显示要求：

- 运行中使用 reasoning Mark 和轻量动画。
- Reasoning 内容允许多行，使用 trace Markdown 样式。
- 不使用单行 `text-overflow: ellipsis` 截断完整思考内容。
- 不为每个 Token/Delta 重复显示“模型思考”。
- 没有 reasoning 内容时显示阶段文案，例如“正在思考”，不生成假内容。
- 完成后图标和文字弱化，保留可读内容。

#### Tool Row

Tool Row 按同一个 `tool_call_id` 原位更新：

```text
requested  → 准备调用
running    → 正在调用
progress   → 更新进度和安全摘要
completed  → 已完成，可展开结果摘要
failed     → 失败，显示安全错误摘要
cancelled  → 已取消
```

显示结构：

```text
[图标] 搜索健康资料  [睡眠改善]  已完成  ⌄
       └─ 找到 6 条参考内容
```

规则：

- 工具动作名称不截断。
- 查询词、文件名等脱敏内容以 Chip 展示，空间不足时 Chip 可截断。
- 原始 arguments 不进入 DOM。
- 工具结果只显示安全摘要，完整领域结果由独立业务卡片承载。
- 同一 ToolCall 不同时显示 requested、running、completed 三行。
- Progress 事件只更新现有 Row，不增加轨迹数量。

#### 排序规则

轨迹排序使用：

```text
round_index ASC
  → Round Row rank=0
  → Tool Row rank=1, call_index ASC
  → Observation/公开结果 rank=2（如作为独立 Row）
```

相同排序键使用稳定 ID 作为最终比较项。Replay、刷新或 Live 更新后顺序必须完全一致，不能按事件到达时间重新排列已经显示的 Row。

#### 涉及文件与修复方向

| 文件 | 修复方向 |
|---|---|
| `chat_sync/ai_runtime/agentic/loop.py` | 为每轮提供稳定 `round_id/index`，把 ToolCall 关联到当前 Round |
| `chat_sync/ai_services/stream_writer.py` | `agent.round.*` Event 输出稳定 Round 字段和 reasoning/narration channel |
| `chat_sync/ai_services/tool_state_service.py` | Tool Event 持续携带 `tool_call_id`、`round_index`、`call_index`，同调用原位收敛 |
| `chat-web/lib/chat/turn-trace-reducer.ts` | 按 `round_id` 归并 reasoning，按 `tool_call_id` 归并工具状态，拒绝 Delta 级 Row |
| `chat-web/lib/tools/tool-activity-reducer.ts` | requested/running/progress/terminal 合并为一个 ToolActivityDTO |
| `chat-web/lib/chat/turn-presentation.ts` | 将 Round 与 Tool Row 按稳定排序规则组合成 Turn Trace |
| `chat-web/components/chat/turn/TurnTrace.tsx` | 渲染 Round/Tool/Observation 层级，最终答案不进入 Trace |
| `chat-web/components/chat/turn/TurnTraceRow.tsx` | 增加工具 Chip、进度、终态、折叠详情和错误安全摘要 |
| `chat-web/components/chat/turn/PublicThinkingCard.tsx` | 同 Round 内流式增长，不为每个 reasoning Delta 新建卡片 |
| `chat-web/app/globals.css` | 对齐 DeepTutor 11px trace Markdown、14px Row、15px 图标、弱化终态和竖线布局 |

#### 为什么必须按实体分组

- Provider reasoning 可能产生数百个 Delta，按 Delta 建 Row 会造成大量 DOM 和视觉噪声。
- Tool progress 可能频繁上报，必须原位更新才能表达“同一个任务正在推进”。
- Agent Round 是 Think/Act/Observe 循环的真实边界，按 Round 分组才能看出工具调用前后的思考变化。
- 稳定 ID 合并使 WebSocket Replay 不产生重复步骤。
- 最终答案独立于 Trace，才能保持 reasoning 与正式答复的阅读边界。

#### 轨迹分组验收场景

1. 同 Round 100 个 reasoning Delta 最终只产生一条 Reasoning Row。
2. 同 ToolCall 的 requested、running、10 个 progress、completed 最终只产生一条 Tool Row。
3. 一轮并行 3 个工具产生 3 条 Tool Row，并按 `call_index` 排序。
4. 工具完成后的下一轮模型调用产生新的 Reasoning Row。
5. WebSocket 重复事件不增加 Row 或重复文本。
6. 乱序事件 Replay 后恢复稳定顺序。
7. 最终回答只显示在正文，不在 Trace 中重复。
8. 工具原始参数、内部错误和未脱敏结果不进入 DOM。

### 4.5 补充确认：工具轨迹与最终工具结果卡分层展示

#### 为什么要确认这个问题

同一次工具调用同时包含两类不同的信息：

1. **过程信息**：调用了什么工具、正在执行还是已经完成、耗时多久、是否失败。
2. **业务结果**：检索资料、健康数据、文件、图片、可视化、任务结果，或需要用户继续操作的内容。

如果只展示轨迹，用户只能知道系统“做过什么”，无法直接使用工具产出的结构化结果；如果把轨迹、通用工具结果卡和领域业务卡全部无条件展示，同一结果又会重复。因此确认对齐 DeepTutor，采用“过程轨迹 + 有价值的业务结果卡”两层结构。

#### 已确认的目标结构

```text
AssistantTurn
├── AssistantActivity / TraceFlow
│   └── Tool Trace Row              # 工具名称、状态、耗时、安全摘要
├── Final Answer                    # AI 最终文字回答
└── ToolPresentationSlot
    └── Business Result Card(s)     # 有阅读或操作价值的结构化结果
```

展示规则：

- 每个工具调用保留一条稳定的 Tool Trace Row，表达 `requested/running/completed/failed/cancelled` 生命周期。
- 只有具备独立阅读价值或交互价值的结果才渲染业务结果卡，例如知识检索摘要、健康数据卡、文件、图片、可视化、任务结果、授权卡或等待用户输入卡。
- 最终回答可以概括工具结论，但不得再次完整复制结构化卡片或原始工具结果。
- 工具失败时，轨迹行展示经过脱敏的失败状态和可行动提示，不生成空白结果卡。
- 多个不同业务结果可以按现有 `order_key` 顺序展示；同一工具调用的通用结果卡与领域结果卡不得重复展示。

#### 结果卡去重规则

去重只使用现有关系字段，不新增关联字段：

```text
callId = block.tool_call_id
      ?? block.parent_tool_call_id

domainCallIds = 所有领域业务结果 Block 的 callId 集合

若通用 tool result Block.callId 存在于 domainCallIds：
    保留 Tool Trace Row
    保留领域业务结果卡
    隐藏通用工具结果卡
否则：
    保留 Tool Trace Row
    仅在通用结果本身具有用户价值时展示通用结果卡
```

边界说明：

- 轨迹行不参与结果卡去重。同一工具调用同时出现一条轨迹行和一张业务结果卡属于预期结果。
- 领域卡已经完整表达结果时，不再额外显示通用 `tool` 结果卡。
- 同一工具返回多个不同且有价值的领域 Block 时，可以全部展示，并按 `order_key` 稳定排序。
- 去重仅影响 Web 的展示选择，不删除或改写服务端 canonical Block，也不影响 iOS 拉取结果。

#### 数据模型约束：保持现有模型不变

本项不得修改消息数据模型，必须继续以 iOS 当前可解析的 canonical 模型为唯一事实源：

1. 不新增 Message 字段、Block kind、NodeRole、数据库列或 Web-only payload。
2. 继续使用现有 `tool_call_id`、`parent_tool_call_id`、`parent_block_id`、`node_role`、`anchor`、`order_key`、`revision`、`status` 建立关系和排序。
3. 过程 Block 继续使用现有 `timeline/tool` 语义，业务结果 Block 使用现有 `toolPresentation` 语义；JSON 枚举值必须遵守当前 iOS 契约。
4. 业务结果继续使用现有 `ChatMessageBlockPayload` 分支及 `payload.<snake_case>._0` 编码规则，不创建第二套 Web payload。
5. `reasoning_delta`、`tool_call_delta` 等 Runtime Event 只负责实时传输；最终仍投影到现有 canonical Message/Block，不成为第二套持久化模型。
6. Web 可以在内存中派生 `TurnPresentation`、`TraceRowViewModel` 等视图模型，但不得将其写回服务端或同步给 iOS。

#### 后端落地方向

| 文件/模块 | 修复方向 | 明确禁止 |
|---|---|---|
| `chat_sync/ai_services/tool_state_service.py` | 工具执行状态继续投影到现有工具 Block；领域结果通过已有 `tool_call_id/parent_tool_call_id` 关联原调用 | 新建 Web 专用 ToolResult 表或消息结构 |
| `chat_sync/ai_services/stream_writer.py` | 按现有事件序号发布工具状态和业务结果 Block 更新，保证实时流与重放顺序一致 | 在每个流事件中重复发送整份工具结果 |
| `chat_sync/contracts/canonical.py` | 仅校验已有 kind、NodeRole、payload 和关联字段，防止 iOS 契约漂移 | 为 Web 新增专属枚举值 |
| 工具 Adapter | 将原始结果转换为已有领域 payload，并在输出前完成脱敏与裁剪 | 下发原始参数、密钥、内部 URL 或未经脱敏的健康数据 |

后端必须保证同一 Tool Call 的状态 Block 和业务结果 Block 使用一致的现有调用关联标识。Outbox 重放、断线恢复和历史拉取后，该关联关系不得丢失。

#### Web 落地方向

| 文件/模块 | 修复方向 |
|---|---|
| `chat-web/lib/chat/turn-presentation.ts` | 从同一组 canonical Blocks 派生 activity、answer、presentation 三个展示区域，并按调用关联标识去重结果卡 |
| `chat-web/components/chat/turn/TurnTraceRow.tsx` | 只展示工具过程、状态、耗时和安全摘要，不承担完整业务结果展示 |
| `chat-web/components/chat/turn/ToolPresentationSlot.tsx` | 展示筛选后的领域结果卡，继续通过现有 Block Registry/Adapter 分发 |
| Block Registry/Adapter | 将现有 payload kind 映射到对应结果卡，不新增第二套消息类型判断 |

结果卡选择应实现为只读的纯派生逻辑：输入当前消息已有 Blocks，输出轨迹 Block 和待展示结果 Block。该逻辑不得修改输入数据，也不得持久化 Web 视图状态。

#### 验收场景

1. 搜索工具产生领域检索卡时，显示一条搜索轨迹和一张检索结果卡，不再显示重复的通用工具卡。
2. 工具只有执行状态、没有用户可读结果时，仅显示轨迹，不出现空结果卡。
3. 同一工具返回多个互不重复的业务结果 Block 时，按现有 `order_key` 展示。
4. 工具失败时显示一条失败轨迹；错误内容已脱敏，且不生成空白业务卡。
5. 页面刷新、WebSocket 重连和历史回放后，轨迹与结果卡的数量、顺序和关联保持一致。
6. Web 展示去重不修改服务端原始 Block，不影响 iOS 同步和解码。
7. canonical 契约快照、数据库 Schema 和 iOS 数据模型对比均无新增字段或枚举值。

## 五、目标组件结构

```text
AssistantTurn
└── message__content
    ├── TurnActivity
    │   ├── ActivityMark
    │   ├── status label
    │   ├── duration
    │   ├── chevron（仅存在轨迹时）
    │   └── TraceFlow
    ├── AssistantResponse
    ├── ToolPresentationSlot
    ├── TurnActions
    └── TurnUsageSummary
```

状态图标选择：

| 回合阶段 | 唯一图标 | 动画 |
|---|---|---|
| thinking / exploring | `ReasoningMark` | 呼吸 + 轻微缩放 |
| using_tools | `ToolMark` | 呼吸或工具运行状态动画 |
| composing | `RespondingMark` 或产品确认的回答图标 | 呼吸 |
| completed | `RespondedMark` | 静态 |
| failed / cancelled | 对应终态图标 | 静态 |

## 六、具体落地方案

### 6.1 `AssistantTurn.tsx`

文件：`chat-web/components/chat/turn/AssistantTurn.tsx`

改动方向：

- 删除助手 `<article>` 下的 `message__avatar` 节点。
- 删除该文件不再使用的 `Sparkles` import。
- `message__content` 成为助手回合唯一内容容器。
- Activity、正文、工具结果、操作和 Usage 保持既有顺序。
- 不在无 Activity 的历史消息上补回头像。

目标伪结构：

```tsx
<article className="message message--assistant">
  <div className="message__content">
    <div className="message__body">
      <TurnActivity />
      <AssistantResponse />
      <ToolPresentationSlot />
    </div>
    <TurnActions />
    <TurnUsageSummary />
  </div>
</article>
```

### 6.2 `ChatMessages.tsx`

文件：`chat-web/components/chat/home/ChatMessages.tsx`

改动方向：

- 历史助手消息和 Live 助手消息统一经过 `AssistantTurn`。
- 检查备用/离线分支，删除其中直接渲染的固定助手头像。
- 空 active Run 只渲染一个 `AssistantTurn + TurnActivity`，不得留下头像占位。
- 保证用户消息右对齐逻辑不受影响。
- 不改变 canonical Block 的读取和归属逻辑。

### 6.3 `TurnActivity.tsx`

文件：`chat-web/components/chat/turn/TurnActivity.tsx`

改动方向：

- Activity Mark 成为整个助手回合的唯一主图标。
- 图标视觉尺寸以 22px 为目标，点击热区由整个状态头提供。
- 轨迹竖线中心与图标中心严格对齐。
- 没有可展开轨迹时不显示 Chevron，状态头不伪装成可展开按钮。
- 完成态关闭呼吸动画。
- 后续按 `CHAT-WEB-027` 接入 Reasoning/Tool/Responded 三类 Mark。

### 6.4 `globals.css`

文件：`chat-web/app/globals.css`

改动方向：

- 删除或停止使用 `.message__avatar` 在助手回合中的布局占位。
- 将 `.message--assistant` 的横向 gap 清零或改为不依赖头像列。
- 保持 `.message__content` 最大宽度和响应式规则。
- Activity、最终正文、操作栏和 Usage 使用同一左边界。
- 校准 `.turn-activity__body-inner` 的 `margin-left`、`border-left` 和 `padding-left`，让竖线从 22px Mark 中线自然下垂。
- 小屏幕不得因移除头像后出现正文贴边，应由消息列的页面 padding 控制安全边距。

### 6.5 无障碍

- Activity Mark 保持 `aria-hidden="true"`，避免屏幕阅读器重复朗读图标含义。
- 状态头通过可见文案和 `aria-live="polite"` 表达“正在探索/正在使用工具/已完成”。
- 有轨迹时使用 Button，并提供 `aria-expanded`、唯一 `aria-controls`。
- 没有轨迹时使用非交互状态容器，不提供无效的折叠按钮。
- 删除头像后不得损失助手回合的 `article` 语义或可定位名称。

## 七、禁止的修复方式

- 不允许只设置 `.message__avatar { visibility: hidden; }`，这仍会保留布局宽度。
- 不允许仅把头像 SVG 改成透明色。
- 不允许删除 Activity Mark 而保留固定头像；这会失去思考、工具和完成状态语义。
- 不允许为历史消息和 Live 消息保留两套不同结构。
- 不允许修改 iOS 消息模型来控制 Web 头像显示。
- 不允许新增 Web 专用 Block kind 或 Message 字段。
- 不允许修改后端 Run/Event 数据来解决纯前端布局问题。

## 八、影响范围

直接影响：

- 普通文本助手回复。
- 正在生成的空助手回合。
- Agentic 工具回合。
- 历史助手消息。
- 失败、中断、取消和完成状态。
- 对话列表的横向对齐及响应式宽度。

不应影响：

- 用户消息气泡。
- Composer、Sidebar 和 Header。
- Tool Block、健康卡片和可视化卡片的数据结构。
- WebSocket、Event Replay 和流式正文内容。
- 复制、重生、删除和反馈业务命令。

## 九、测试要求

### 9.1 组件测试

- `AssistantTurn` DOM 中不存在 `.message__avatar`。
- 运行中的助手回合只存在一个 Activity Mark。
- 完成态助手回合只存在一个 Responded Mark。
- 空 active Run 不渲染悬空图标。
- 历史和 Live 助手消息 DOM 主结构一致。
- 无 Trace 时不显示 Chevron，状态头不可无效展开。

### 9.2 视觉回归

至少保存以下截图：

1. 新对话刚发送、尚未收到正文。
2. 正在思考且没有工具。
3. 正在执行工具并展开 Trace。
4. 最终回答开始流式。
5. 完成态且 Trace 折叠。
6. 历史完成消息。
7. 失败、中断和取消状态。
8. 桌面宽屏与窄屏。

视觉门禁：

- 同一回合不得出现重复星芒图标。
- Activity Mark、状态文字和轨迹竖线处于同一视觉轴。
- 最终正文与 Activity 左边界一致。
- 移除头像后页面不能出现异常向左跳动。

### 9.3 回归测试

- 用户消息仍保持右对齐。
- Markdown、工具结果卡和 Usage 不改变内容。
- 流式更新不会因组件结构变化中断。
- 点击 Activity 不触发发送、取消或其他回合命令。
- 键盘和屏幕阅读器可以操作有轨迹的 Activity。

## 十、验收标准

- [ ] 所有助手回合均删除固定左侧头像。
- [ ] 一个助手回合最多显示一个主 Activity Mark。
- [ ] 运行中、工具中、回答中和完成态图标语义明确。
- [ ] 不再出现悬空头像或重复星芒。
- [ ] Activity 图标、状态、计时、Chevron 和竖线对齐 DeepTutor。
- [ ] Activity、正文、工具卡、操作和 Usage 使用同一左边界。
- [ ] 历史消息与 Live 消息使用同一助手回合结构。
- [ ] 运行状态依次显示“小鲸探索中… / 正在调用工具… / 小鲸正在回答…”。
- [ ] 完成态统一显示“已完成 · Ns”，并停止呼吸动画。
- [ ] 运行中耗时每秒更新，终态以服务端耗时冻结校正。
- [ ] 页面不再同时出现 Activity 状态头和重复 `generation-status`。
- [ ] 缺少可靠历史耗时时不伪造秒数。
- [ ] 普通对话和工具对话统一进入同一 Agentic Stream Pipeline。
- [ ] 工具列表为空只表示 `tools=[]`，不切换执行实现。
- [ ] Provider 生成期间持续产生真实 reasoning/text Delta，不在完整回答后伪切片。
- [ ] reasoning 写入 canonical deepThought Block，最终回答写入 canonical text Block。
- [ ] reasoning 与最终答案在 Event、Reducer 和 UI 中保持分离。
- [ ] system/developer prompt、密钥、内部 URL、工具原始参数和未脱敏健康数据不进入思考区域。
- [ ] 模型没有 reasoning 时只显示状态文案，不编造思考内容。
- [ ] iOS `ChatMessage.swift` 现有字段可以直接解码 Web 新生成的消息。
- [ ] 删除只服务于完成后字符切片的冗余配置。
- [ ] reasoning、工具执行阶段思考区域默认展开。
- [ ] 首个已确认 canonical text Delta 到达时思考区域自动折叠。
- [ ] narration 不得错误触发自动折叠。
- [ ] 用户手动开合后，本条消息生命周期内用户选择优先。
- [ ] 历史完成回合默认折叠，失败/中断/取消回合默认展开。
- [ ] 开合状态不写入 iOS 数据、服务端持久化或 LocalStorage。
- [ ] 一个 Agent Round 只产生一条 Reasoning Row，同 Round Delta 原位追加。
- [ ] 一个 ToolCall 只产生一条 Tool Row，所有生命周期状态原位更新。
- [ ] 多工具按 round_index/call_index 稳定排序，Replay 后顺序一致。
- [ ] 工具查询或文件摘要以脱敏 Chip 展示，原始 arguments 不进入 DOM。
- [ ] 最终答案不在 Trace 中重复展示。
- [ ] 每个工具调用保留一条过程轨迹，仅有价值的领域结果生成业务卡。
- [ ] 同一 ToolCall 已有领域结果卡时，不重复展示通用工具结果卡。
- [ ] 工具失败或没有用户可读结果时，不生成空白结果卡。
- [ ] 轨迹与结果卡使用现有 `tool_call_id/parent_tool_call_id` 关联，不增加数据字段。
- [ ] Web 结果卡筛选只产生内存派生视图，不改写 canonical Block。
- [ ] iOS Canonical 数据模型和服务端协议零改动。
- [ ] 组件、视觉、响应式和无障碍测试通过。

## 十一、后续问题

本工单已经确认六项相互依赖的问题：固定助手头像与 Activity 图标重复、回合状态头/动态耗时缺失、reasoning/text 单一真实流式管线、思考区域自动开合规则、Agent Round/ToolCall 轨迹分组，以及“过程轨迹 + 有价值的业务结果卡”分层与去重。后续 DeepTutor 对齐问题继续采用一问一答方式确认，并继续遵守 iOS canonical 数据模型不变的边界。
