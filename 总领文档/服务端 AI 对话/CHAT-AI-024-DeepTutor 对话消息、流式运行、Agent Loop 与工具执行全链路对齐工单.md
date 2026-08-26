# CHAT-AI-024 DeepTutor 对话消息、流式运行、Agent Loop 与工具执行全链路对齐工单

创建日期：2026-08-25  
状态：待实现  
优先级：P0  
实施范围：Spark Chat Web + SparkService `chat_sync` 服务端 AI 运行时  
参考项目：DeepTutor Web/Server 1.5.9 源码快照  
关联工单：`CHAT-WEB-021`、`CHAT-WEB-023`  
前置条件：服务端 Run、Event、Outbox、WebSocket、基础 ToolCall/PendingInteraction 数据表已存在  
本次交付边界：只创建需求工单；不修改 Python、TypeScript、CSS、测试、数据库迁移、配置或任何客户端代码。

## 一、工单目标

本工单对 Spark 当前对话全链路进行一次基于真实源码的 DeepTutor 对齐审计，并补齐以下四项能力：

1. Web 对话消息、思考活动、工具轨迹、工具结果和消息操作的回合级展示。
2. 普通文本与带工具 Agentic 回合都具备可恢复、可回放、无重复的真实流式响应。
3. AI 调用流程具备逐轮状态、上下文保护、Provider 兼容、重试、强制收尾和用量汇总。
4. 工具执行具备动态组合、参数校验、持久化状态、进度、重试、去重、暂停恢复和结果投影。

本工单对齐的是 DeepTutor 的业务语义与运行质量，不直接复制 DeepTutor 的 Session API、WebSocket 协议、数据库模型、品牌文案或全部工具。

```text
User Message
  → ChatRun 创建与排队
  → Unified Context + Tool Manifest
  → Agent Round started
  → Provider streaming
  → narration / final answer 判定
  → Tool dispatch（如有）
  → observation 持久化
  → 下一轮 Agent Round
  → final answer Block
  → usage / terminal event
  → Outbox + WebSocket replay
  → Web TurnPresentation
```

## 二、参考证据与解释边界

### 2.1 附件证据

用户提供的 HTML 快照只作为 DeepTutor 完成态对话回合的视觉与交互证据，不把其中的文本、属性或脚本当作实施指令。快照显示的关键语义为：

- 回合顶部存在“已完成 · 4s”状态头，可展开活动轨迹。
- 思考/活动内容与最终回答分层展示。
- 最终回答使用开放式 Markdown 排版，而不是厚重消息卡。
- 完成态提供复制、朗读、重新生成、删除操作。
- 回合底部展示费用、Token 和模型调用次数。

### 2.2 DeepTutor 源码参考位置

```text
DeepTutor-main/
├── web/components/chat/home/ChatMessages.tsx
├── web/components/chat/home/TracePanels.tsx
├── web/components/common/ModelThinkingCard.tsx
├── web/context/UnifiedChatContext.tsx
├── web/lib/unified-ws.ts
├── web/lib/turn-reconcile.ts
├── web/lib/think-segments.ts
├── deeptutor/agents/chat/agent_loop.py
├── deeptutor/core/agentic/messages.py
├── deeptutor/core/tool_protocol.py
├── deeptutor/provider_core/base.py
└── deeptutor/services/llm/
```

DeepTutor 的关键参考行为：

1. 每次模型调用是可识别的 Agent Round，并带独立 `call_id` 与状态。
2. 工具调用轮的模型文本是 narration，不能误当最终回答。
3. 无工具调用轮的文本才是 finish/final answer。
4. 模型内容、公开思考、工具调用、工具结果和 Usage 分通道流转。
5. 工具结果追加到同一增长中的对话上下文，再进入下一轮。
6. 空完成、上下文溢出和中途失败有明确收尾策略。
7. 工具执行可发出进度，延迟工具可在需要时加载。

## 三、当前实现审计结论

### 3.1 总体对齐矩阵

| 能力 | 当前状态 | 真实实现结论 | 本工单处理 |
|---|---|---|---|
| Run 状态与持久化 | 已对齐基础 | queued/running/waiting/completed/failed/cancelled/interrupted 已存在 | 保留并补逐轮状态 |
| Event/Outbox/Replay | 已对齐基础 | 有持久事件、sequence、Outbox、WS replay | 补新事件并验证终态收敛 |
| 纯文本流式输出 | 基本对齐 | 50ms/256 字节批量写入 Block，失败可中断 | 补首 Token、Usage 和恢复验收 |
| Agentic 流式输出 | 未对齐 | Agent Loop 调用未接入 `on_chunk`，最终文本一次性写入 | P0 阻断修复 |
| Agentic Usage | 未对齐 | Round 收集 Usage，但 Loop/Task 未累计；终态可能为 0 | P0 阻断修复 |
| 回合 Trace/角色 | 未对齐 | 无 round started/delta/completed、narration/finish 语义 | 新增公开回合事件 |
| Web 回合卡片 | 部分对齐 | 有 Tool Activity，但没有统一状态、思考、耗时、Usage | 新建 TurnPresentation |
| 历史 reasoning/usage | 未对齐 | Sync DTO 已有字段，Web 未消费；运行时也未完整写入 | 打通读写链路 |
| Provider 兼容 | 部分对齐 | 兼容工具函数存在，但没有接入真实调用链 | 接入适配管线 |
| 上下文保护 | 部分对齐 | 首轮构建有预算，工具结果增长后无逐轮窗口保护 | 每轮调用前 guard/fold |
| 工具注册/组合 | 部分对齐 | 有 Registry/Policy/Composition，实际注册工具有限 | 建立能力矩阵与动态组合 |
| 工具校验/并发/超时 | 基本对齐 | 有 schema、size、semaphore、timeout | 补重试、取消、跨轮去重 |
| 工具状态落库 | 基本对齐 | ToolCall/ToolResult Block 与事件已存在 | 补 progress 与事务收敛 |
| 延迟工具 | 未完全对齐 | 有 DeferredToolService，但模型不能在同一 Run 内 `load_tools` | 增加 Run 内加载语义 |
| ask_user/客户端工具 | 基本框架存在 | PendingInteraction + checkpoint + resume 已存在 | 补跨 Worker/多设备验收 |
| 独立心跳 | 未对齐 | 心跳依赖流式 chunk/步骤，慢 Provider/工具可能超过租约 | 增加 Run 级后台心跳 |
| 费用展示 | 未对齐 | Usage 表有 amount/currency，Runtime 未计价，Web 未展示 | 增加安全 Usage Summary |

### 3.2 已对齐部分：不得重复重写

以下能力应复用 Spark 当前实现，不迁移 DeepTutor 同名基础设施：

- `ChatRun`、`ChatRunEvent`、`ChatEventOutbox`、`ChatUsageRecord` 数据模型。
- Run REST 创建、查询、取消、重生和 active-run 查询。
- `StreamWriter` 的 durable event、Block 投影、Outbox 事务写入。
- Web `event-reducer` 的 sequence/event ID/revision 幂等处理。
- OpenAI-compatible SSE 解析、首事件超时和空闲超时基础实现。
- Tool Registry、Scoped Registry、Policy、Composition、Dispatcher、Executor 的现有骨架。
- ToolCall、PendingInteraction、checkpoint 和 resume 数据结构。
- Web Block Registry 及 iOS 兼容业务卡片类型。

禁止为“看起来更像 DeepTutor”而另建第二套 Run、Session、Message、Event 或 WebSocket 事实源。

### 3.3 明确不对齐部分

- 不展示或持久化模型隐藏 Chain-of-Thought、system prompt、developer prompt、内部 scratchpad。
- 不复制 DeepTutor 的账号、Session、权限、计费、知识库或文件存储模型。
- 不一次性迁移 DeepTutor 全部工具；每个工具必须通过 Spark 的数据权限、隐私和风险审查。
- 不把 Provider 原始请求、密钥、内部 URL、健康数据原文写入公开事件。
- 本工单不修改 iOS、Android、HarmonyOS 的 UI 或登录流程。
- 本工单不改动 `bootstrap`、`api_key` 或服务端 Run 开关配置。

## 四、目标目录与职责

### 4.1 Spark Web

```text
chat-web/
├── components/chat/home/
│   ├── ChatMessages.tsx                  # 历史/live Message 合并入口
│   ├── ChatBlockRenderer.tsx             # Block Registry 分派
│   └── ActivityDisclosure.tsx            # 当前工具活动折叠器，逐步退役为兼容层
├── components/chat/turn/
│   ├── AssistantTurn.tsx                 # [建议新增] 完整助手回合外壳
│   ├── TurnActivityHeader.tsx             # [建议新增] 状态、耗时、折叠控制
│   ├── TurnTrace.tsx                      # [建议新增] Round/Tool/Observation 轨迹
│   ├── TurnActions.tsx                    # [建议新增] 复制/朗读/重生/删除/反馈
│   └── TurnUsageSummary.tsx               # [建议新增] Token/调用/费用
├── lib/chat/
│   ├── turn-presentation.ts              # [建议新增] Message/Block/Event → ViewModel
│   ├── turn-trace-reducer.ts             # [建议新增] Round/Tool 公开轨迹投影
│   └── answer-text.ts                    # [建议新增] 复制/朗读的纯正文提取
├── context/RunControlContext.tsx          # Run 命令、WS、replay/poll
├── lib/event-reducer.ts                   # wire event 幂等 reducer
├── types/chat.ts                          # Turn/Usage/Trace UI 类型
├── types/run.ts                           # Run Event 契约
└── tests/
    ├── turn-presentation.test.ts
    ├── turn-trace-reducer.test.ts
    ├── agentic-stream-replay.test.ts
    └── turn-actions.test.tsx
```

### 4.2 SparkService 后端

```text
chat_sync/
├── ai_runtime/agentic/
│   ├── loop.py                           # 有界循环、空完成、强制收尾、恢复轮次
│   ├── round_runner.py                   # 单次 Provider 流、角色、Usage
│   ├── checkpoint.py                     # 语义 checkpoint/fold
│   └── think_filter.py                   # 公开正文与隐藏 reasoning 分离
├── ai_runtime/providers/
│   ├── openai_compatible.py              # SSE/原生 tool calls
│   ├── request_compat.py                 # 请求能力降级
│   ├── reasoning_params.py               # 模型 reasoning 参数适配
│   ├── context_window.py                 # route/model 窗口解析
│   ├── dsml_tool_calls.py                # [按模型新增] DSML 兼容
│   └── error_mapping.py                  # 可重试错误分类
├── ai_runtime/tools/
│   ├── registry.py
│   ├── composition.py
│   ├── deferred.py
│   ├── dispatcher.py
│   ├── executor.py
│   └── adapters/
├── ai_services/
│   ├── stream_writer.py                  # Round/Block/Usage/terminal durable events
│   ├── tool_state_service.py             # Tool 状态与公开投影
│   ├── pending_interaction_service.py
│   └── context/context_builder.py
├── ai_tasks/
│   ├── run_tasks.py                      # Run Worker 与 Agent callback 编排
│   ├── recovery_tasks.py                 # lease/queued/waiting 恢复
│   └── outbox_tasks.py                   # durable relay
├── ai_api/
│   ├── views.py                          # Run/Turn commands
│   └── serializers.py
└── tests/
    ├── ai_runtime/test_agentic_stream.py
    ├── ai_runtime/test_agentic_recovery.py
    ├── ai_runtime/test_tool_dispatcher.py
    ├── ai_services/test_turn_projection.py
    └── contracts/
```

### 4.3 依赖方向

```text
Provider raw chunks
  → RoundRunner 标准化
  → AgentLoop 决定 narration / finish / tool_calls
  → RunTask semantic callbacks
  → StreamWriter durable events + Blocks
  → Outbox
  → WebSocket/replay
  → event-reducer
  → turn-presentation
  → AssistantTurn
```

UI 不解析 Provider 数据；Provider 不写数据库；Tool Adapter 不直接发 WebSocket；所有公开实时状态必须先成为可回放的 Spark Event 或 Block 投影。

## 五、能力一：Web 对话消息与回合卡片对齐

### 5.1 当前问题

当前 `ChatMessages.tsx` 可以合并历史 Block 和 live Block，也能渲染正文及工具卡，但还存在以下缺口：

1. `ActivityDisclosure` 只理解 `toolCall/toolResult`，没有完整回合状态、Round、公开思考、耗时和完成摘要。
2. `reasoning_content`、`reasoning_duration_ms`、`usage_summary` 已出现在 Sync 类型/响应中，但 Web 消息层未形成统一消费路径。
3. 工具 Block 被整体提升到正文前方，不能准确表达“模型说明 → 工具 → 观察 → 下一轮”的顺序。
4. 助手操作目前不完整；历史消息缺少稳定的 Run/Message 所有权，重生、删除不能只依赖当前 active Run。
5. 缺少朗读、回合费用/Token/调用次数和失败态完整操作。

### 5.2 目标回合结构

```text
AssistantTurn
├── TurnActivityHeader       已完成 · 4s / 正在调用工具 / 等待你的回复
├── TurnTrace (collapsible)
│   ├── AgentRound           公开思考摘要或阶段
│   ├── ToolCall             工具名称、脱敏参数摘要、状态
│   ├── Observation          公开结果摘要
│   └── AgentRound           正在组织最终回答
├── FinalAnswer              Markdown / structured Blocks
├── TurnActions              复制 / 朗读 / 重生 / 删除 / 反馈
└── TurnUsageSummary         ¥/$、tokens、calls、tools
```

### 5.3 展示规则

1. 生成中活动区默认展开；终态且存在最终回答后自动折叠。
2. 用户手动切换折叠状态后，本条回合不再被自动规则覆盖。
3. 没有公开思考内容时，只展示事实状态，不生成伪造的“思考过程”。
4. `reasoning_content` 仅允许承载 Provider 明确标记可公开的 reasoning summary；原始隐藏推理不得进入该字段。
5. 工具轨迹与工具业务结果卡分层：轨迹说明执行过程，结果卡承载文件、图表、健康资料等业务内容。
6. 最终回答复制/朗读必须排除工具参数、内部 Trace 和隐藏数据。
7. 流式、回放、刷新后三种来源必须生成同一个 `TurnPresentation`。
8. 无正文但处于 waiting/failed/cancelled 时仍显示完整回合外壳。

### 5.4 消息操作

| 操作 | 规则 | 服务端要求 |
|---|---|---|
| 复制 | 复制最终可见正文，不含 Trace | 无 |
| 朗读 | 使用浏览器 SpeechSynthesis 朗读纯文本；不支持时隐藏 | 无，不上传内容 |
| 重新生成 | 基于目标历史 Run/assistant message 创建新分支 | 请求必须携带目标 `run_id`/message ID，不能使用任意 active Run |
| 删除 | 删除完整用户-助手回合，使用 tombstone/显式命令 | 活跃 Run 先取消；事务更新消息及 Thread head |
| 反馈 | 绑定稳定 assistant message/run | 幂等写入，不能跟随当前选中 Run 漂移 |

Sync Message 的安全公开投影建议增加或补齐：

```json
{
  "turn_summary": {
    "run_id": "uuid",
    "status": "completed",
    "started_at": "...",
    "finished_at": "...",
    "duration_ms": 4210,
    "regenerate_allowed": true,
    "delete_allowed": true,
    "usage": {
      "prompt_tokens": 5100,
      "completion_tokens": 800,
      "reasoning_tokens": 0,
      "tool_calls": 1,
      "model_calls": 2,
      "amount": "0.0009",
      "currency": "USD"
    }
  }
}
```

费用只有在 `price_version` 和可靠计价来源都存在时展示；否则只展示 Token/调用次数，不显示 `0.0000` 伪费用。

### 5.5 Web 文件改动方向

| 文件 | 改动方向 |
|---|---|
| `chat-web/components/chat/home/ChatMessages.tsx` | 只负责 Message/Block 分组，改由 `AssistantTurn` 渲染完整回合 |
| `chat-web/components/chat/home/ActivityDisclosure.tsx` | 兼容旧 Tool Block；新事件启用后迁移到 `TurnTrace` |
| `chat-web/components/chat/turn/*` | 新增回合头、Trace、操作和 Usage 组件 |
| `chat-web/lib/chat/turn-presentation.ts` | 统一历史、live、replay 的纯函数投影 |
| `chat-web/lib/event-reducer.ts` | 支持 Round/Trace/Usage 增量，保持 sequence 幂等 |
| `chat-web/types/chat.ts`、`types/run.ts`、`types/sync.ts` | 增加公开 TurnTrace/TurnSummary 类型 |
| `chat-web/lib/api/run-api.ts` | 历史 Run 重生/取消参数显式化 |
| `chat-web/lib/api/chat-sync-api.ts` | 增加回合删除命令或安全 tombstone API |

## 六、能力二：真实流式响应与事件契约

### 6.1 当前根因

纯文本路径会把 Provider chunk 交给 `AsyncTextDeltaBuffer`，因此具备真实流式体验；但 Agentic 路径调用 `run_agentic_loop()` 时没有传递语义化的 chunk callback，导致：

- 带工具回合的模型文本和 reasoning 不会实时进入 Event/Block。
- 最终回答只能在 `on_final_text` 时一次性写入。
- Round 返回的 Usage 没有被 Run Task 汇总。
- Web 无法知道某段文本属于工具前 narration 还是最终回答。

因此“纯文本能流式”不能视为“AI 对话已完成流式对齐”。

### 6.2 目标事件契约

在现有 Run Event envelope 上扩展下列公开事件；所有事件包含 `event_id`、`run_id`、`thread_id`、`sequence`、`occurred_at`、`payload_version`：

| Event | durable | 关键 payload | Web 行为 |
|---|---:|---|---|
| `agent.round.started` | 是 | `round_id/index/call_id` | 新建运行中 Trace Row |
| `agent.round.delta` | 是或批量 durable | `round_id/channel/text_delta` | 显示 provisional 公开内容 |
| `agent.round.completed` | 是 | `round_id/call_role/finish_reason/usage` | narration 留在 Trace；finish 提升为正文 |
| `agent.round.failed` | 是 | `round_id/error_code/retryable` | Row 失败态 |
| `tool_call.requested` | 已有 | call/tool/public args | 工具等待态 |
| `tool_call.started` | 已有 | attempt/start | 工具运行态 |
| `tool_call.progress` | 新增 | public message/percent | 更新同一工具 Row |
| `tool_result` | 已有 | public result/ref | 工具完成态/业务卡 |
| `block.created/delta/...` | 已有 | Block 投影 | 最终持久正文 |
| `usage.updated` | 新增可选 | 累计 tokens/calls | 更新运行中摘要 |
| `usage.final` | 已有补强 | 完整 Usage/费用来源 | 终态摘要 |

`agent.round.delta.channel` 只允许：

- `public_reasoning_summary`：Provider 明确可公开的摘要。
- `assistant_content`：该 Round 的候选内容。

禁止发送 raw chain-of-thought。工具轮结束后，将本轮 `assistant_content` 标为 `narration` 留在 Trace；无工具轮标为 `finish` 并投影到最终 Text Block。这样既能实时显示，又不会把工具前说明重复写入最终答案。

### 6.3 一致性与回放

1. Round delta 使用稳定 `round_id + offset/revision`，重复和倒序必须可忽略。
2. `agent.round.completed(call_role=finish)` 与最终 Text Block 落库必须在同一事务边界或通过可恢复投影收敛。
3. Web 收到 finish promotion 时不得再次拼接已经显示的 provisional 文本。
4. WebSocket 断线后按 sequence replay；replay 完成再合并 live event。
5. 即使 Outbox 终态丢失，Run 查询也必须允许 Web 合成 terminal UI 并停止 loading。
6. `run.completed` 前必须完成 delta flush、Block complete、Usage final 和 Message 状态投影。
7. 客户端收到未知事件必须忽略并记录诊断，不能使整个 reducer 崩溃。

### 6.4 流式性能约束

- 文本批量刷新目标：50–100ms 或 128–512 字符，二者先到即 flush。
- 首 Token 指标从 Provider 首个有效公开 delta 计算。
- 不为每个字符创建数据库 Event。
- Run 级独立心跳每 10–15 秒续租，不能依赖 Provider 或 Tool 是否产生 chunk。
- 慢工具、等待网络和模型静默期间仍需续租；取消后心跳立即停止。
- 单 Run 全局 deadline、单 Provider 调用 deadline、单 Tool deadline 分开配置。

## 七、能力三：AI 调用流程与 Agent Loop 对齐

### 7.1 目标状态机

```text
claim Run
  → start heartbeat
  → load snapshot/checkpoint
  → build/restore context
  → resolve provider + tool manifest
  → for round from checkpoint.next_round_index to max_rounds
       → guard context window
       → emit round.started
       → stream provider response
       → normalize usage/tool calls
       → if tool calls
            classify narration
            dispatch tools
            append observations
            save checkpoint
            continue
         else if non-empty answer
            classify finish
            commit final Block
            complete Run
         else
            one empty-finish nudge
  → if max rounds or recoverable mid-loop failure
       forced finish without tools
  → terminal persistence
  → stop heartbeat
```

### 7.2 必须补齐的运行规则

1. **逐轮 Usage**：`round_runner` 返回的 prompt/completion/reasoning tokens 与模型调用次数必须累加到 Run Usage；工具次数由成功/失败 ToolCall 事实统计。
2. **逐轮上下文保护**：每次 Provider 调用前重新计算窗口。工具结果过大时先引用化/折叠，不只在首轮 ContextBuilder 裁剪一次。
3. **空完成处理**：没有 tool call 且正文为空时，只允许追加一次明确 nudge；仍为空则使用稳定错误码失败，禁止无限调用。
4. **中途收尾**：已有有效 observation 时发生可恢复 Provider 错误，可尝试一次禁用工具的 forced finish；失败后保留 partial trace 并标记 interrupted/failed。
5. **最大轮次**：达到预算后不再允许工具，执行一次 forced finish；仍无结果则终止。
6. **恢复轮次**：resume 必须从 `checkpoint.next_round_index` 开始，轮次和工具预算不能重新归零。
7. **Checkpoint folding**：不能简单保留最后 N 条；要保留 system、最近用户目标、未完成 ToolCall、关键 observation 引用和已生成摘要。
8. **Provider 重试**：只在尚未向用户提交不可逆公开内容且错误可重试时自动重试；已经流出内容时进入 interrupted/recovery，不静默重放造成重复。
9. **并行 Tool Calls**：只有 Provider 和本轮 Tool Policy 都支持并行时才发送 `parallel_tool_calls=true`。
10. **取消**：每轮、每个 Tool 前后检查 cancel_requested；取消要终止 Provider stream、工具任务和后台心跳。

### 7.3 Provider 兼容接入

当前 `request_compat.py`、`reasoning_params.py`、`context_window.py` 等辅助模块不能只存在于目录和单测中，必须进入真实请求管线：

```text
ai_config/model route
  → ProviderCapabilities
  → reasoning params normalization
  → request compatibility plan
  → tool schema/image/stream_options capability filtering
  → context window guard
  → provider stream
  → normalized chunks/errors/usage
```

兼容降级顺序必须可观察且有上限：

1. `stream_options` 不支持时仅移除该字段重试一次。
2. 某模型不支持 tools 时不得伪装为工具模型；回到纯文本或显式拒绝能力。
3. tool schema 不兼容时记录具体 schema/tool，不静默删除全部工具后生成误导答案。
4. DSML tool call 只对配置明确允许的模型启用，原生 tool call 优先。
5. 图片/附件降级必须保留用户可理解的引用说明，不把二进制或本地路径写入 prompt。
6. Provider 错误统一映射为稳定 Spark error code、retryable 和 public message。

### 7.4 后端核心文件改动方向

| 文件 | 改动方向 |
|---|---|
| `chat_sync/ai_runtime/agentic/round_runner.py` | 暴露语义 chunk、Round Usage、finish reason、tool call 完整性 |
| `chat_sync/ai_runtime/agentic/loop.py` | 接收 Round callback；实现角色判定、空完成、forced finish、恢复预算 |
| `chat_sync/ai_runtime/agentic/checkpoint.py` | 保存 next round、累计预算、manifest hash、folded context |
| `chat_sync/ai_tasks/run_tasks.py` | 接通 Agentic 流、Usage、独立 heartbeat、取消与 terminal 顺序 |
| `chat_sync/ai_runtime/providers/openai_compatible.py` | 接入 ProviderCapabilities 与兼容降级 |
| `chat_sync/ai_runtime/providers/request_compat.py` | 从孤立辅助函数变成真实请求适配步骤 |
| `chat_sync/ai_runtime/providers/reasoning_params.py` | 按模型路由生成合法 reasoning 参数 |
| `chat_sync/ai_runtime/providers/context_window.py` | 每轮提供模型窗口与输出预算 |
| `chat_sync/ai_services/stream_writer.py` | 新增 Round/Usage 事件与 final promotion 原子写入 |
| `chat_sync/ai_tasks/recovery_tasks.py` | 补 queued stale、运行中租约、等待交互超时的差异化恢复 |

## 八、能力四：工具执行对齐

### 8.1 当前工具范围

Spark 当前服务端注册表以医疗/成员/来源与客户端桥接为主，已有或可见的能力包括：

- `ask_user`
- 当前成员、成员资料
- 健康来源、健康资源上下文、`read_source`
- iOS HealthKit/定位等客户端执行工具

DeepTutor 还包含 brainstorm、web/paper search、web fetch、RAG/知识库、memory、exec、notes、GitHub、sub-agent、图像/视频等通用工具。它们不能因为“对齐”被整包复制。

### 8.2 工具能力分级

| 级别 | 处理方式 | 示例 |
|---|---|---|
| A：现有 Spark 工具 | 本工单直接对齐运行语义 | member/health/read_source/ask_user/client tools |
| B：已有后端能力但未接 Agent | 建 Adapter 后接入 | Spark 文件、知识库、任务只读能力 |
| C：需外部 Provider/MCP | 通过 Deferred/Capability 加载 | web_search、paper_search、GitHub |
| D：高风险执行 | 单独安全工单，不在本工单开放 | exec、写文件、外部写入、代替用户操作 |
| E：不属于 Spark 产品范围 | 明确保持不迁移 | DeepTutor 专属教学业务工具 |

### 8.3 目标工具生命周期

```text
ToolCallRequest
  → schema validation
  → policy/permission/source/platform check
  → execution_key + cross-round dedup
  → ToolCall requested/running
  → run heartbeat + cancellation scope
  → adapter execution
  → progress events
  → result size/security projection
  → ToolResult persisted
  → observation appended to Agent context
  → checkpoint committed
```

### 8.4 必须补齐的业务规则

1. `max_attempts` 不能只落库不执行；仅对明确 retryable、幂等或有 idempotency key 的工具重试。
2. 去重范围必须覆盖同一 Run 的不同 Round 和恢复执行，不限于单次 dispatch batch。
3. `execution_key` 由 run、tool、规范化参数 hash、业务作用域组成；恢复后相同调用直接复用已完成结果。
4. 工具进度只发布公开摘要、百分比和阶段；raw stdout、健康原文、密钥与内部错误不可公开。
5. 结果超过上下文预算时，保存完整结果引用，只把摘要和 resource ref 放入 observation。
6. 工具调用状态和结果 Block 必须终态收敛；Worker 崩溃后不能永久显示 running。
7. Run 取消必须向可取消 Adapter 传播；不可取消工具完成后不得继续推进已取消 Run。
8. ask_user/客户端工具进入 waiting 时保存 checkpoint；回复必须校验 interaction、device/session、version 与一次性消费。
9. 多设备同时提交回复时只允许一个成功，其他返回稳定冲突码并刷新 Run 状态。
10. Tool Policy 同时考虑 target、risk、permission、platform、member/source scope 和 feature flag。

### 8.5 `load_tools` 与延迟工具

当前 Deferred Tool 更接近“在外部请求中预加载，下一个上下文构建时可见”，尚未达到 DeepTutor 同一 Run 内动态加载。目标流程：

```text
模型仅看到短工具目录 + load_tools
  → 调用 load_tools(names=[...])
  → DeferredToolLoader 校验 capability/policy
  → 返回精确工具 schemas
  → 当前 Agent Loop 更新本轮可用 manifest
  → 保存 manifest hash/checkpoint
  → 下一 Round 可调用新工具
```

限制：

- 一次加载数量、总 schema token、来源和 TTL 必须受限。
- 恢复 Run 时按 checkpoint 中的 manifest 版本重建，不能因部署漂移改变语义。
- 外部 MCP/Provider 不可用时返回结构化 observation，不让整个 Run 无原因 500。
- 动态工具仍走 Spark Registry/Policy/Dispatcher，不允许绕过审计直接调用。

### 8.6 工具文件改动方向

| 文件 | 改动方向 |
|---|---|
| `chat_sync/ai_runtime/tools/composition.py` | 输出带来源、风险、能力版本的 manifest |
| `chat_sync/ai_runtime/tools/deferred.py` | 支持同一 Run 内加载与 checkpoint 恢复 |
| `chat_sync/ai_runtime/tools/dispatcher.py` | Run 级去重、预算、并行策略和取消 |
| `chat_sync/ai_runtime/tools/executor.py` | retry policy、progress callback、结果引用化 |
| `chat_sync/ai_services/tool_state_service.py` | progress/attempt/terminal 事务投影 |
| `chat_sync/ai_runtime/tools/public_projector.py` | 按工具生成安全参数/结果摘要 |
| `chat_sync/ai_models/tool.py` | 必要时补 progress、execution key 唯一性和 artifact refs |
| `chat-web/lib/tools/tool-activity-reducer.ts` | 合并 requested/started/progress/result/cancelled |
| `chat-web/components/chat/turn/TurnTrace.tsx` | 展示公开工具生命周期，不解析 raw result |

## 九、阶段拆分与实施顺序

### CHAT-AI-024A：契约与回合投影基线

阶段目标：先冻结跨端语义，避免 Web 和后端分别猜测。

- 定义 Round/Trace/Usage Event schema 与版本。
- 定义 narration、finish、public reasoning summary 的含义。
- 定义 `TurnSummary`、回合操作权限和费用缺失语义。
- 增加 Python/TypeScript 共用 fixtures、未知事件和旧版本兼容测试。
- 不开放新 UI feature flag。

出口门禁：相同 fixture 在 Python contract test 与 Web reducer test 中通过。

### CHAT-AI-024B：Agentic 真流式与恢复

阶段目标：服务端带工具和不带工具都能流式、回放、正确终止。

- 接通 Round semantic callbacks 与 Usage 累计。
- 实现 narration/final promotion、空完成、forced finish。
- 接入独立 heartbeat、取消和 resume round budget。
- 每轮执行 context guard 与 checkpoint fold。
- 补 Provider 兼容适配真实调用链。

出口门禁：至少覆盖无工具、单工具、多轮工具、断线回放、重试、取消、超时、Worker 重启八类集成测试。

### CHAT-AI-024C：工具执行一致性

阶段目标：工具生命周期不会重复执行、永久 running 或泄露敏感数据。

- Run 级 execution key 与跨轮/恢复去重。
- policy-aware retry、progress、结果引用化。
- waiting interaction 的多 Worker/多设备竞争测试。
- 首批 A/B 级工具清单验收。
- 同一 Run `load_tools` 作为独立 feature flag 灰度。

出口门禁：故障注入后 ToolCall、Run、Event、Block 四者终态一致。

### CHAT-AI-024D：Web 回合卡片与操作

阶段目标：对齐附件展示语义并消费真实服务端事件。

- 建 `TurnPresentation` 和统一 `AssistantTurn`。
- 上线状态头、Trace、公开思考、工具轨迹、最终正文。
- 上线复制、朗读、历史 Run 重生、回合删除、反馈。
- 上线可靠 Usage；费用无可靠数据时自动隐藏。
- 保留旧事件/旧消息兼容渲染。

出口门禁：流式、刷新、回放、历史加载的同一回合截图与可访问树一致。

### CHAT-AI-024E：生产加固与清理

阶段目标：完成可观测、灰度、回滚和旧兼容层退役。

- 指标、告警、SLO、压测和故障演练。
- 按账号/模型/工具灰度新 Agentic 流。
- 验证后移除重复的 Tool-only 活动拼装和未使用 helper。
- 保留一版旧事件读取，不再写旧事件。

出口门禁：连续灰度期内无 Run 永久 running、重复正文、重复工具执行或 Usage 明显丢失。

## 十、核心伪代码

### 10.1 Agent Loop

```python
async def run_agentic(run, checkpoint, context, manifest):
    budget = checkpoint.restore_budget()
    for index in range(checkpoint.next_round_index, budget.max_rounds):
        await cancellation.raise_if_requested(run.id)
        context = await context_guard.fit(context, manifest, budget)
        round_id = stable_round_id(run.id, index)
        await events.round_started(round_id, index)

        result = await round_runner.stream(
            context=context,
            tools=manifest.schemas,
            on_public_delta=lambda chunk: events.round_delta(round_id, chunk),
        )
        budget.add_usage(result.usage)

        if result.tool_calls:
            await events.round_completed(round_id, call_role="narration", usage=result.usage)
            observations = await dispatcher.dispatch(run, result.tool_calls)
            context = context.append(result.message, observations)
            await checkpoint.save(index + 1, context, budget, manifest)
            continue

        if result.text.strip():
            await writer.commit_final_round(round_id, result.text, result.usage)
            return

        if budget.consume_empty_finish_nudge():
            context = context.append_empty_finish_nudge()
            continue
        raise EmptyModelCompletion()

    await forced_finish_without_tools(context, budget)
```

### 10.2 Web Turn Projection

```ts
function projectTurn(message, blocks, events): TurnPresentation {
  const trace = reduceTurnTrace(events, blocks)
  const finalBlocks = selectFinalPresentationBlocks(blocks, trace)

  return {
    id: message.server_message_id,
    runId: message.turn_summary?.run_id ?? null,
    status: deriveStatus(message, trace),
    activity: derivePublicActivity(trace),
    finalBlocks,
    actions: deriveAllowedActions(message.turn_summary),
    usage: normalizeUsage(message.usage_summary, message.turn_summary?.usage),
  }
}
```

## 十一、异常与恢复矩阵

| 场景 | 目标结果 |
|---|---|
| Provider 首 Token 前超时 | 可重试时有限重试；Web 保持 running/重试状态 |
| 已流式后连接中断 | Run interrupted；保留已提交 Trace/正文，不自动重复追加 |
| 工具执行超时 | ToolCall failed/timeout，observation 可供模型解释或进入 forced finish |
| Worker 在工具完成后、checkpoint 前崩溃 | execution key 复用结果，不重复执行副作用 |
| Worker 静默超过租约 | Recovery 校验独立心跳后再中断/接管 |
| Outbox 暂时失败 | Event 保持 durable，重试 relay；Web 可 REST replay |
| WebSocket 断线 | 从最后 sequence 重连；重复事件被 reducer 忽略 |
| ask_user 回复竞争 | 第一个合法回复成功，其余 409/稳定业务码 |
| 用户取消时工具仍运行 | 停止推进 Run；工具结果标记 late/ignored，不生成回答 |
| Usage 缺失 | UI 显示“用量暂不可用”或隐藏，不显示伪 0 |
| 旧历史消息没有 RunSummary | 兼容展示正文和 Block，禁用无法安全执行的历史操作 |

## 十二、安全、隐私与权限

1. Event 与日志只写公开投影；工具 raw args/result 使用服务端受控存储并按需引用。
2. 健康资料、成员、附件和来源工具必须继承 ContextBuilder 的成员/来源授权，不因 Agent 调用绕过。
3. Web 端不能自行声明自己拥有 HealthKit、定位或移动端权限。
4. 删除/重生/回复 PendingInteraction 必须校验 Thread/Run 归属和 Web session。
5. 费用摘要不得暴露 Provider Key、采购价规则、内部 route 名或敏感调试字段。
6. Markdown/HTML、工具结果和链接继续经过安全清洗。
7. `exec`、外部写入、账号操作等高风险工具必须单独安全评审，不随本工单默认开启。

## 十三、测试与验收

### 13.1 后端自动化测试

- 纯文本 100+ delta 合批、顺序、最终文本一致。
- Agentic 单工具轮：narration 不进入 final answer。
- Agentic 多工具多轮：Round、Tool、Observation 顺序一致。
- Provider 原生 tool call 分片组装与配置限定的 DSML fallback。
- 每轮 Usage 累计，最终 model_calls/tool_calls 正确。
- 空完成一次 nudge，第二次稳定失败。
- max round forced finish。
- 工具结果导致上下文溢出时 fold/reference。
- 慢 Provider、慢 Tool 期间 lease 不过期。
- Worker 崩溃恢复不重复执行工具。
- cancel/timeout/outbox failure/replay 收敛。
- raw reasoning、工具敏感字段不会进入公开事件。

### 13.2 Web 自动化测试

- 同一 Run 的 live、replay、Sync history 生成相同 `TurnPresentation`。
- running 默认展开、completed 自动折叠、用户手动状态优先。
- narration/工具/observation/final 的可访问顺序正确。
- 复制和朗读只得到最终正文。
- 历史重生绑定目标 Run，不绑定当前 active Run。
- 删除回合的确认、loading、失败回滚和成功移除。
- Usage 缺失、部分存在、完整计价三种展示。
- 未知新 Event、旧 Message、单 Block 损坏时安全降级。
- reduced motion、键盘操作、屏幕阅读器标签和焦点恢复。

### 13.3 端到端场景

1. 无工具提问，边生成边显示，刷新后文本完全一致。
2. 一次搜索/资料读取，先显示工具活动，再显示最终回答。
3. 多工具回合，工具 narration 不混入最终复制文本。
4. ask_user 暂停，刷新/换 Worker 后回复并继续。
5. iOS 客户端工具请求在 Web 上显示“需在移动端完成”，不会误执行。
6. 生成中断线 10 秒后重连，无重复字符和重复工具卡。
7. 历史回合重生形成新分支，旧回答保留。
8. 删除历史回合后多端 Sync 一致。

### 13.4 验收指标

| 指标 | 目标 |
|---|---|
| Run 永久 running | 0 |
| 同一 event 重放导致重复文本 | 0 |
| 同一 execution key 重复副作用 | 0 |
| Agentic 首公开增量 P95 | 与纯文本路径同量级，单独设阈值 |
| completed Run 缺 final Block | 0 |
| completed Run 缺 terminal event | 0 |
| Usage model call 计数与真实调用不一致 | 0（允许明确 unavailable） |
| 公开事件敏感字段泄露 | 0 |

## 十四、可观测性与上线门禁

建议新增指标：

- `chat_agent_round_total{role,provider,model}`
- `chat_agent_round_latency_seconds`
- `chat_agent_empty_finish_total`
- `chat_agent_forced_finish_total{reason}`
- `chat_tool_execution_total{tool,status,attempt}`
- `chat_tool_dedup_hit_total`
- `chat_run_heartbeat_lag_seconds`
- `chat_run_recovery_total{reason,result}`
- `chat_stream_first_public_delta_seconds`
- `chat_stream_replay_gap_total`
- `chat_usage_unavailable_total{provider,model}`

日志关联键统一使用 `request_id/run_id/thread_id/round_id/call_id/tool_call_id/event_id`；不记录 prompt、Token、authorization、健康原文或工具 raw result。

上线必须采用独立 feature flags：

```text
CHAT_AGENT_ROUND_EVENTS_ENABLED
CHAT_AGENTIC_STREAM_ENABLED
CHAT_TOOL_PROGRESS_ENABLED
CHAT_DEFERRED_LOAD_TOOLS_ENABLED
CHAT_WEB_TURN_PRESENTATION_ENABLED
CHAT_WEB_TURN_ACTIONS_ENABLED
CHAT_WEB_USAGE_SUMMARY_ENABLED
```

灰度顺序：内部账号 → 指定模型 → 只读工具 → 少量 Web 用户 → 全量 Web。任何阶段出现重复工具执行、Run 无终态、正文重复或敏感字段泄露，立即关闭对应新 flag；不回滚数据库事实。

## 十五、Definition of Done

只有同时满足以下条件，本工单才可关闭：

- [ ] 普通文本与 Agentic 路径都存在真实流式公开增量。
- [ ] 每个 Agent Round 有稳定 ID、状态、角色和 Usage。
- [ ] 工具前 narration 不会进入最终回答或复制文本。
- [ ] Run replay/刷新/实时三条路径展示结果一致。
- [ ] Web 回合卡片包含状态、活动、最终正文、操作和可靠 Usage。
- [ ] 历史重生、删除绑定明确 Run/Message，不依赖当前 active Run。
- [ ] Tool retry、去重、取消、progress、result projection 和崩溃恢复通过测试。
- [ ] 每轮上下文 guard、空完成和 forced finish 通过故障测试。
- [ ] 慢 Provider/Tool 不会因缺少 chunk 导致错误租约过期。
- [ ] 隐藏 reasoning、敏感工具参数和健康原文不进入公开事件。
- [ ] 旧消息和旧事件仍可安全展示。
- [ ] 指标、告警、灰度和回滚开关具备可操作性。

## 十六、实施边界确认

本工单只定义后续实现要求。创建本工单时：

- 未修改 Spark Web 源码。
- 未修改 SparkService 后端源码。
- 未修改数据库迁移、配置、feature flag 或 `bootstrap`。
- 未修改 iOS、Android、HarmonyOS 客户端及其登录/会话流程。
- 未启动或开放任何 DeepTutor 工具。

