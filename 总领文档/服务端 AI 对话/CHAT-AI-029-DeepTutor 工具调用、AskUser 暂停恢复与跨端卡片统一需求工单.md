# CHAT-AI-029 DeepTutor 工具调用、AskUser 暂停恢复与跨端卡片统一需求工单

创建日期：2026-08-27  
状态：待契约收敛与跨端实现  
优先级：P0  
阶段归属：P4 服务端 Agentic 工具、P5 等待与客户端工具  
父工单：`CHAT-AI-024`  
关联工单：`CHAT-DATA-025`、`CHAT-DATA-026`、`CHAT-WEB-023`、`CHAT-WEB-027`  
参考实现：DeepTutor `ToolResult.pause_for_user`、Agent Loop、Tool Registry、Tool Dispatcher、StreamBus  
实施约束：本文件只创建需求工单，不修改 Python、TypeScript、CSS、数据库迁移、配置或任何客户端代码。

## 一、工单目标

本工单将 SparkService 的工具调用收敛为一套服务端主导、模型决策、跨客户端共享的统一协议，并以 `ask_user` 为第一条完整验收链路。

目标结果：

1. 工具由模型基于服务端提供的 Tool Schema 自主决定是否调用，与 DeepTutor 一致。
2. `ask_user` 暂停当前 Run，用户回答后恢复同一个 Agent Loop，不创建新的对话 Run。
3. `target` 成为所有工具共有的执行目标字段，服务端在把 Tool Schema 发送给模型前完成平台隔离和过滤。
4. 模型参数经过 Tool Schema 与 ToolPolicy 两层校验后才能执行。
5. ToolResult 同时进入模型上下文、持久化事件和跨端安全卡片投影。
6. Web、iOS、Android、HarmonyOS 从同一 Run/Event/Block/PendingInteraction 事实源恢复相同状态。
7. 工具活动卡、交互卡和领域结果卡分层，不展示原始参数、健康原文或内部错误。

```text
Model decides tool_call
  -> Spark validates Tool Schema + ToolPolicy
  -> target router chooses server / client path
  -> ToolCall persisted
  -> execute or pause
  -> ToolResult / PendingInteraction persisted
  -> Event + canonical Block projection
  -> Web/iOS/Android/HarmonyOS render
  -> role=tool appended to checkpoint
  -> same Agent Loop resumes
  -> final answer
```

## 二、已经确认的产品与架构决策

### 2.1 谁决定调用工具

**问题：AI 工具到底由谁决定调用？**

**已确认答案：** 模型决定，与 DeepTutor 一致。

为什么必须明确：如果由 Web 或任一客户端根据文本猜测是否调用工具，不同客户端会形成不同运行逻辑，无法共享 Run、ToolCall 和卡片状态。

边界：

- 服务端决定本轮向模型提供哪些工具。
- 模型决定是否调用、调用哪个工具以及提供什么参数。
- 服务端拥有最终执行权，可以因权限、上下文、平台、风险或开关拒绝模型请求。
- 客户端不解析模型文本来触发工具。
- Provider 原始工具协议只存在于 Provider Adapter 内部，客户端不直接接触。

### 2.2 `ask_user` 的运行语义

**问题：`ask_user` 是普通工具结果，还是暂停当前回合？**

**已确认答案：** 暂停当前 Run；用户恢复消息后继续同一个 Agent Loop。

为什么必须明确：如果把问题当作普通最终回答，用户回复会创建新 Run，之前已经完成的工具调用、上下文和模型 transcript 无法可靠恢复。

目标流程：

```text
模型 tool_call(name=ask_user)
  -> 服务端校验 ask_user 参数
  -> 创建 ChatPendingInteraction
  -> ChatToolCall.status = waiting_for_user
  -> ChatRun.status = waiting_for_user_input
  -> 保存 ChatAgentCheckpoint
  -> 释放 Worker lease
  -> 发送 interaction.requested + run.waiting
  -> 投影 toolQuestionCards
  -> 用户提交选项/文本
  -> 校验 owner/run/interaction/key/tool/questions/expiry/idempotency
  -> 将回答写入 role=tool 消息
  -> Run 重新排队
  -> resume_chat_run 领取同一个 Run
  -> 从 checkpoint 恢复同一个 Agent Loop
  -> 模型继续调用工具或输出最终答案
```

### 2.3 回答归属

**问题：用户回答如何保证回到正确的 Run？**

**已确认答案：** 每张问答卡必须携带并提交以下稳定字段：

```text
run_id
interaction_id
interaction_key
tool_call_id
question_ids
expires_at
schema_version
```

为什么必须明确：用户可能刷新页面、切换客户端、打开多个标签页或重复提交。只凭当前 Thread 或当前 active Run 不能证明回答属于哪一次工具调用。

服务端必须同时校验：

- 当前用户拥有 interaction 对应的 Thread 和 Run。
- Run ID、Interaction ID、Interaction Key 和 Tool Call ID 形成同一条持久化关系。
- 提交的 question IDs 是请求 Schema 的子集且无重复。
- Interaction 仍为 `pending/claimed`，尚未解决或过期。
- Run 仍处于对应 waiting 状态。
- `schema_version` 与服务端一致。
- `Idempotency-Key` 存在且同键同内容才允许重放。
- 第一份合法回复胜出，其他设备获得稳定冲突响应。

### 2.4 参数校验

**问题：工具参数由谁校验？**

**已确认答案：** 两层校验后才能执行。

```text
LLM Tool Schema validation
  -> Spark ToolPolicy validation
  -> Tool Adapter execution
```

为什么必须明确：模型输出不是可信输入。即使 Provider 接受了 Schema，也可能返回额外字段、错误类型、越权 ID、超长数组或不属于当前 Snapshot 的资源标识。

第一层负责结构：

- JSON Object 类型。
- required 字段。
- string/integer/number/boolean/array/object 类型。
- enum、items、maxLength、maxItems、additionalProperties。
- 参数总字节数。

第二层负责业务和权限：

- 工具是否在本轮 Scoped Registry 中。
- 工具版本和 schema hash 是否匹配。
- target、platform 和 capability 是否允许。
- required_permissions 是否满足。
- required_context 是否存在。
- member/source/file/resource 是否属于当前用户和 Context Snapshot。
- risk、side_effect、timeout、attempt、result budget 是否允许。

### 2.5 服务端工具与客户端工具隔离

**问题：服务端工具和客户端工具如何区分？**

**已确认答案：** 所有工具共有 `target` 字段，值只能为 `server` 或 `client`；服务端在发送 Tool Schema 给模型之前按 target 和当前客户端能力直接过滤。

为什么必须明确：HealthKit、定位和系统权限只能由受支持客户端执行；Web 不能执行、模拟或伪造这些结果。

规则：

- `target=server`：只能由 Celery Run Worker 内的 Tool Adapter 执行。
- `target=client`：服务端不得调用 Adapter 读取本机能力，只能创建 `client_tool` PendingInteraction。
- `target` 不能由模型参数覆盖。
- `target` 不能由客户端上报任意改写。
- Provider 收到的是经过过滤的标准 OpenAI Tool Schema，不需要看到 Spark 内部 target 元数据。
- 未通过 target/platform/capability 过滤的工具不进入本轮 Provider 请求。

`ask_user` 的标准定义为：

```text
target=server
execution_mode=pause
interaction_kind=ask_user
```

`pause` 不是第三种 target。target 只回答“在哪里执行”，execution mode 回答“执行后是否暂停”。

示例：

| 工具 | target | execution_mode | Web 本轮 Tool Manifest |
|---|---|---|---|
| `read_source` | server | immediate | 满足 source context 时提供 |
| `web_search` | server | immediate | 开关、权限和 Provider 就绪时提供 |
| `ask_user` | server | pause | waiting 功能开启时提供 |
| `fetch_step_details` | client | pause | Web 无合格移动执行器时过滤 |
| `get_current_location` | client | pause | Web 无合格移动执行器时过滤 |
| `write_memory` | server | immediate/consent | 写权限和确认策略通过后提供 |

客户端工具目标流程：

```text
模型请求 target=client 工具
  -> 服务端再次验证 target/platform/capability
  -> 创建 client_tool PendingInteraction
  -> Run.status = waiting_for_client_tool
  -> 合格客户端 claim
  -> 客户端检查 OS 权限和业务授权
  -> 客户端执行
  -> 回传 ToolResult + claim token + nonce/idempotency
  -> 服务端校验设备会话、claim、时效、Schema 和数据边界
  -> 写入 role=tool
  -> 恢复 Agent Loop
```

Web 没有 HealthKit 时：

- 不得把 HealthKit 工具 Schema发送给模型，除非同一账号存在已声明能力且可 claim 的移动执行器。
- 工具设置或能力说明可以展示“该工具需要受支持的移动端授权”。
- 不得返回模拟步数、睡眠、能量或定位数据。

### 2.6 工具卡片安全投影

**问题：哪些数据可以展示在工具卡片中？**

**已确认答案：** 只展示服务端生成的安全投影。

```json
{
  "tool_call_id": "call_123",
  "display_name": "读取睡眠数据",
  "status": "completed",
  "display_args": {
    "range": "最近 7 天"
  },
  "result_preview": "已读取 7 天睡眠记录",
  "source_refs": []
}
```

禁止进入 DOM、公开 Event 或跨端 Block：

- 原始 arguments。
- Token、claim token、nonce 和 device secret。
- 完整健康原始数据与未裁剪 samples。
- Provider 请求和响应原文。
- system/developer prompt 和隐藏 reasoning。
- 内部异常堆栈、内部 URL 和文件系统路径。
- 无必要的数据库主键集合。
- 未经权限裁剪的成员、文件和健康资料字段。

### 2.7 ToolResult 双路径

**问题：工具结果如何进入模型上下文？**

**已确认答案：** 同一 ToolResult 同时走模型观察路径和客户端展示路径，但两条路径的数据职责不同。

```text
ToolResult.content
  -> role=tool message
  -> Agent Checkpoint transcript
  -> Agent Loop 下一轮模型上下文

ToolResult.metadata
  -> durable Event / canonical Block
  -> Web、iOS、Android、HarmonyOS 卡片

ToolResult.sources
  -> source_refs / citations
  -> 引用卡片与最终答案引用

ToolResult.pause_for_user
  -> PendingInteraction
  -> waiting state / resume
```

为什么必须明确：卡片内容不能替代模型 observation，模型 observation 也不能原样暴露给 UI。两者需要关联同一个 tool_call_id，但使用不同安全预算。

## 三、DeepTutor 对齐基线

### 3.1 直接对齐的语义

| DeepTutor 能力 | Spark 对齐要求 |
|---|---|
| 模型从 Tool Schema 自主选择工具 | Provider 请求使用 `tools + tool_choice=auto` |
| `ToolResult.content` 进入 role=tool | checkpoint 保存标准 Tool message |
| `pause_for_user` 保持当前 Turn 存活 | 持久化 Run waiting，恢复同一 Run |
| Tool Registry 提供统一定义 | Spark Registry + ToolPolicy + Scoped Registry |
| Dispatcher 处理并发和重复调用 | Spark 落库 ToolCall 并保证幂等 |
| AskUser 一次调用包含多题 | 统一 questions 数组，1–4 题 |
| 第二个并行 ask_user 被折叠 | 同一模型批次只允许一个 pause owner |
| Agent Loop 有最大轮次 | 超限后 tools=[] 强制完成 |
| StreamBus 分离 content/tool/progress | Spark durable Event/Block/Outbox 对应语义 |

### 3.2 不直接迁移的部分

- 不迁移 DeepTutor 进程内 reply queue 作为生产事实源。
- 不迁移 DeepTutor PocketBase/SQLite Session 存储。
- 不迁移 DeepTutor WebSocket 协议和 Web 组件。
- 不迁移全部工具或默认授权策略。
- 不允许 DeepTutor StreamBus 替代 Spark Event/Outbox。
- 不复制 DeepTutor 的账号、文件、知识库和健康权限模型。

Spark 必须使用 MySQL 中的 Run、Checkpoint、ToolCall、PendingInteraction、Event 和 Block 恢复跨 Worker/跨设备状态。

### 3.3 DeepTutor 复用决策：直接复用、部分迁移与禁止迁移

**已确认答案：** 不迁移 DeepTutor 整个 Agent 进程；只迁移已经验证过的协议、纯函数和算法语义，再由 SparkService 的 Run、数据库、Worker 和 Event 架构承载生命周期。

| DeepTutor 部分 | 迁移方式 | SparkService 落点 | 迁移要求 |
|---|---|---|---|
| `ToolDefinition`、`ToolParameter` | 直接复用语义，重建 DTO | `chat_sync/ai_runtime/protocols/tool_protocol.py` | 保持 JSON Schema 语义，增加 `target` 等 Spark 字段 |
| `ToolResult` | 直接复用四路语义 | `ai_runtime/providers/types.py`、`ai_models/tool.py` | `content`、`metadata`、`sources`、`pause_for_user` 分离持久化/投影 |
| `ToolPolicy` | 直接复用判定思想，接入 Spark 权限 | `ai_runtime/tools/policy.py` | 绑定用户、Run、平台和权限快照，不能只信模型或客户端 |
| Schema 校验 | 直接复用纯校验规则 | `ai_runtime/tools/dispatcher.py` | 先校验模型参数，再校验服务端 Policy，错误码稳定 |
| 参数 canonical hash | 直接复用算法 | `ai_runtime/tools/dispatcher.py`、`ai_models/tool.py` | 用于重复调用、幂等和审计，不暴露原始参数 |
| `ask_user` payload 规范化 | 直接复用规范化语义 | `ai_runtime/tools/ask_user_schema.py`、`ai_services/pending_interaction_service.py` | 稳定 question_id，限制题数、选项、文本长度和 schema_version |
| 工具重复调用检测 | 直接复用判定算法 | `ai_runtime/tools/dispatcher.py` | 与数据库唯一约束、Worker 重试共同生效 |
| Agent Loop 最大轮次/强制结束 | 直接复用控制算法 | `ai_runtime/agentic/loop.py` | 每 round 产生 checkpoint，终止状态写入 Run/Event |
| Think/Reasoning 流式分类 | 直接复用分类算法 | `ai_runtime/agentic/think_filter.py`、`ai_services/stream_writer.py` | 转换为可回放 Event/Block，不能混入最终正文 |
| `ToolRegistry` | 部分迁移 | `ai_runtime/tools/registry.py` | 加入版本、target、平台、权限、风险和超时元数据 |
| `ScopedToolRegistry` | 部分迁移 | `ai_runtime/tools/scoped_registry.py` | scope 固化为 Run 快照，重试/恢复不能漂移 |
| `dispatch_tool_calls` | 部分迁移 | `ai_runtime/tools/dispatcher.py` | 保留校验、并行、去重，结果必须落库并可恢复 |
| `execute_tool_call` | 部分迁移 | `ai_runtime/tools/executor.py` | server 在 Worker 执行；client 只能生成 PendingInteraction |
| `AgentLoop` | 部分迁移 | `ai_runtime/agentic/round_runner.py`、`loop.py` | 保留 think/act/observe/respond 顺序，由 Run/Checkpoint 驱动 |
| `StreamBus` 事件语义 | 部分迁移 | `ai_models/event.py`、`ai_services/stream_writer.py`、`ai_tasks/outbox_tasks.py` | 保留事件类型/顺序，传输改为 Event + Outbox + Channels，支持 replay |
| Tool prompt hints | 部分迁移 | `ai_services/prompt_assembler.py` | 只注入已过滤 Tool Manifest，不能绕过 target/Policy |
| deferred tools / `load_tools` | 部分迁移 | `ai_runtime/tools/deferred.py`、capabilities | 经 Capability、权限、平台过滤，并记录版本和来源 |
| checkpoint | 部分迁移 | `ai_models/context.py`、`ai_models/run.py` | 由内存对象改为可序列化快照，支持重启、租约恢复和多设备竞争 |

### 3.4 迁移实施规则

1. **先复制测试，再迁移实现。** DeepTutor 纯函数测试先落到 `tests/ai_runtime/`，确认行为基线后再替换 Spark 适配层。
2. **协议优先于类名。** 不要求保留 DeepTutor 类层级，只要求输入、输出、状态迁移和边界条件兼容。
3. **运行时状态不得藏在单例。** 进程内对象只能作为执行器，事实状态必须写入 Run、ToolCall、Checkpoint、PendingInteraction 和 Event。
4. **一次迁移一个边界。** 先完成 `ask_user`，再完成只读 server tool，最后验证一个 client tool pending。
5. **所有迁移保留来源。** 每个迁移文件记录 DeepTutor 源文件、参考版本、Spark 改写原因和许可证核查结果。
6. **不得带入同步调用假设。** Provider 超时、Celery 重试、租约续期、取消和进程崩溃必须有明确状态。
7. **StreamBus 只作为语义参考。** Spark canonical Event/Block 才是 Web、iOS、Android、HarmonyOS 的共享事实源。

### 3.5 迁移验收证据

- 每个“直接复用”条目都有纯函数、边界和 Spark 序列化测试。
- 每个“部分迁移”条目都有适配层测试，证明重试、恢复、取消和多设备竞争不改变语义。
- 每个 DeepTutor 来源文件都有来源清单、许可证记录和对应 Spark 文件路径。
- Provider request snapshot 证明模型只收到过滤后的 Tool Schema。
- AskUser fixture 证明同一 `run_id` 在暂停前后保持不变，且只追加一次 `role=tool` 消息。
- Event/Block fixture 证明 live、replay、历史 Sync 投影一致。
- 删除或替换 DeepTutor 进程内实现后，SparkService 仍能从数据库和 Outbox 恢复未完成 Run。

## 四、当前实现与真实缺口

### 4.1 当前已经具备

- `ToolDefinition/ToolResult/BaseTool` Provider-neutral 协议已存在。
- `ToolPolicy.target` 已支持 `server/client`。
- `ChatToolCall.target` 已持久化。
- Registry、Scoped Registry、Composition、Dispatcher、Executor 已存在。
- `ask_user_schema.py` 已对齐 DeepTutor 的多题结构与长度上限。
- `AskUserTool` 已返回 `pause_for_user`。
- Agent Loop 已能返回 paused outcome。
- `ChatPendingInteraction` 已包含 public ID、interaction key、schema version、过期、claim、response 和幂等字段。
- Run 已支持 `waiting_for_user_input/waiting_for_client_tool`。
- Interaction REST API、resume task、过期恢复任务已存在。
- Web 已有 Tool Activity、Block Registry 和 `toolQuestionCards` renderer 骨架。

### 4.2 当前缺口

1. target 目前分散在 ToolPolicy、ToolCall 和客户端能力中，尚未形成统一 Tool Manifest Entry 契约。
2. Composition 需要提供明确证据，证明 target/client platform 过滤发生在 Provider 请求之前。
3. PendingInteraction 公共 DTO 尚未完整返回 `run_id/interaction_key/question_ids`。
4. `pending_interaction.v1.schema.json` 没有完整覆盖 claimed、interaction key、run ID、questions 和 response 版本。
5. `pause_for_tool()` 当前将等待卡投影为 `searchSummary`，不符合 `ask_user` 卡片语义。
6. 取消逻辑查找 `askUser/clientTool` block kind，但 canonical Block 中不存在这两个 kind，存在投影漂移。
7. canonical Block 已有 `toolQuestionCards`，服务端缺少对应 payload builder 和交互状态投影。
8. Web `ToolQuestionCardsBlock` 当前只是只读列表，不能选择、填写、提交、恢复或展示过期状态。
9. Web 内部 `toolCall/toolResult` 投影不能成为跨端 wire kind；跨端必须继续使用 canonical `tool + toolPresentation`。
10. 安全投影和模型 observation 的字段预算需要分别固化。
11. Web 无客户端工具执行器时的 Manifest 过滤、能力说明和降级文案需要统一。
12. 多标签页、多设备同时回答 AskUser 的竞争验收尚未形成完整契约测试。

## 五、统一 Tool Manifest 契约

### 5.1 服务端内部标准结构

每个工具在 Composition 阶段归一为：

```json
{
  "name": "fetch_step_details",
  "version": "v1",
  "description": "读取授权范围内的步数详情",
  "parameters": {},
  "schema_hash": "sha256",
  "policy_version": "v1",
  "target": "client",
  "execution_mode": "pause",
  "supported_platforms": ["ios"],
  "required_permissions": ["health.steps.read"],
  "required_context": ["member"],
  "risk": "read_only",
  "side_effect": "none",
  "timeout_seconds": 600,
  "max_result_tokens": 1800,
  "max_attempts": 1
}
```

约束：

- `target` 是所有工具必填通用字段。
- 旧注册代码未显式声明时，仅允许在迁移期默认 `server`，并记录告警；契约稳定后取消隐式默认。
- Provider projection 只输出 OpenAI-compatible function schema。
- Spark metadata 不塞入 function arguments，模型不能修改策略字段。
- ToolCall 创建时冻结 target、version、schema hash 和 policy version。
- Run 恢复后使用冻结 Manifest/Checkpoint，不因部署期间 Registry 变化而静默换工具。

### 5.2 Provider 前过滤

```text
Registered tools
  -> capability filter
  -> user enabled tools
  -> context filter
  -> permission/risk filter
  -> target filter
  -> platform/capability filter
  -> deferred/load state filter
  -> freeze manifest hash
  -> OpenAI schemas
  -> Provider
```

Web 场景：

- `target=server` 工具通过其他条件后可以提供。
- `ask_user` 可以提供，因为它由服务端持久化暂停。
- `target=client` 默认过滤。
- 只有同账号存在可验证、在线、支持该 capability 的移动执行器，并且产品允许跨设备 claim 时，才可向模型提供对应 client tool。
- 客户端能力变化只影响新 Round/新 Run；已产生的 PendingInteraction 依照冻结策略完成、拒绝或过期。

## 六、AskUser 契约

### 6.1 请求 Schema

```json
{
  "intro": "为了继续分析，请确认以下信息。",
  "questions": [
    {
      "id": "range",
      "header": "时间范围",
      "prompt": "你希望分析哪个时间范围？",
      "multi_select": false,
      "allow_free_text": true,
      "placeholder": "也可以输入自定义范围",
      "options": [
        {"label": "最近 7 天", "description": "用于观察近期变化"},
        {"label": "最近 30 天", "description": "用于观察月度趋势"}
      ]
    }
  ]
}
```

继续沿用 DeepTutor 规则：

- 一次调用 1–4 个问题。
- 每题最多 8 个选项。
- 问题 ID 稳定、去重。
- 支持单选、多选和自由文本。
- 自动移除重复“其他”选项。
- legacy 单题输入只在服务端边界归一，不扩散到跨端 DTO。

### 6.2 卡片公共 DTO v2

```json
{
  "run_id": "uuid",
  "interaction_id": "uuid",
  "interaction_key": "opaque-stable-key",
  "kind": "ask_user",
  "status": "pending",
  "tool_call_id": "call_123",
  "tool_name": "ask_user",
  "tool_version": "v1",
  "schema_version": 2,
  "question_ids": ["range"],
  "request": {
    "intro": "为了继续分析，请确认以下信息。",
    "questions": []
  },
  "expires_at": "2026-08-28T10:00:00+08:00"
}
```

`interaction_key` 是并发/恢复关联键，不是权限凭证。权限始终由登录用户、Run owner、Thread owner 和服务端记录判断。

### 6.3 回答 DTO

```json
{
  "run_id": "uuid",
  "interaction_key": "opaque-stable-key",
  "schema_version": 2,
  "answers": [
    {
      "question_id": "range",
      "selected_option_indexes": [0],
      "selected_labels": ["最近 7 天"],
      "free_text": ""
    }
  ]
}
```

请求头必须携带新的 `Idempotency-Key`。客户端不得提交未出现在卡片中的 option label，也不得只提交 label 而不提交 index。

### 6.4 状态机

```text
Interaction:
pending
  -> resolved
  -> refused
  -> expired
  -> cancelled

Run:
running
  -> waiting_for_user_input
  -> queued
  -> running
  -> completed / failed / cancelled / interrupted

ToolCall:
running
  -> waiting_for_user
  -> completed / failed / expired / cancelled
```

AskUser 不需要 client claim；同一账号登录的 Web 或移动客户端都可以回答。第一份合法响应在数据库锁内胜出。

## 七、事件与 Block 投影

### 7.1 Durable Events

至少包含：

```text
tool.call.requested
tool.call.started
interaction.requested
run.waiting
interaction.resolved
interaction.refused
interaction.expired
interaction.cancelled
run.resumed
tool.result.completed / tool.result.failed
run.done
```

所有事件必须拥有 run sequence、event ID、payload version，并先落库再通过 Outbox 投递。

### 7.2 三层 UI 结构

```text
活动轨迹层
  canonical tool Block / safe activity projection

交互层
  toolQuestionCards / consent / permission / client pending card

结果层
  searchSummary / structuredHealthCards / visualization / source cards
```

`ask_user` 必须投影为：

```text
kind=toolQuestionCards
node_role=toolPresentation
tool_call_id=<model call id>
status=pending|ready|failed
payload=<canonical tagged union>
```

不得再使用 `searchSummary` 表示“等待用户输入”。取消、过期和解决必须更新同一个 Block ID 与 revision，不创建重复卡片。

### 7.3 Web 卡片行为

Web `toolQuestionCards` 必须支持：

- 单选、多选、自由文本。
- 多问题分步或同页填写。
- 缺失必填项时禁止提交。
- 提交中锁定控件。
- 成功后显示已提交摘要，不再可编辑。
- 409 已被其他设备回答时自动刷新 Interaction 和 Run。
- 410 过期时显示已过期。
- Run 取消时显示已取消。
- 页面刷新后通过 pending API 与 Block 恢复。
- WebSocket 中断时通过 Event replay 恢复。
- 同一个 interaction_id 只渲染一张交互卡。

Web、iOS、Android、HarmonyOS 使用相同 DTO 和状态机；各端可以有不同视觉组件，但不能改变字段和提交语义。

## 八、安全投影与持久化

### 8.1 数据分层

| 数据 | 存储位置 | 是否公开给客户端 | 是否进入模型 |
|---|---|---:|---:|
| 原始 tool arguments | ChatToolCall 受限字段 | 否 | 模型原本已提供 |
| display_args | Event/Block 安全投影 | 是 | 否 |
| ToolResult.content | ToolCall/checkpoint，受预算限制 | 否 | 是 |
| result_preview | Event/Block | 是 | 可选，不作为 observation |
| ToolResult.metadata | 服务端完整 metadata | 默认否 | 否 |
| public metadata | Event/Block 白名单 | 是 | 否 |
| sources/source_refs | ToolCall + 引用投影 | 是，鉴权后 | 是，裁剪后 |
| pause_for_user | PendingInteraction | 安全 Schema 可见 | Agent Loop 控制信号 |

### 8.2 日志要求

允许记录：

- request_id、run_id、tool_call_id、interaction_id。
- tool name/version/target。
- status、duration、attempt、error code。
- schema hash、arguments hash、result size。

禁止记录：

- 原始健康 samples。
- ToolResult.content 原文。
- AskUser 自由文本回答原文。
- token、claim token、nonce、device secret。
- Provider 原始请求和内部异常堆栈。

## 九、错误、幂等、超时与恢复

| 场景 | 服务端行为 | 客户端行为 |
|---|---|---|
| 未知工具 | 安全失败 ToolResult | 工具轨迹显示不可用 |
| Schema 不合法 | 不执行，返回 validation failure | 不展示原始参数 |
| target 不匹配 | 不创建执行任务 | 显示需要支持设备或不可用 |
| 权限不足 | 拒绝或进入 consent | 展示权限说明 |
| ask_user 重复调用 | 第一条成为 pause owner，其余写 duplicate result | 只显示一张卡 |
| 重复回答同内容 | Idempotency replay | 视为成功 |
| 重复回答不同内容 | 409 conflict | 刷新卡片状态 |
| Interaction 过期 | 写 timeout ToolResult，最多恢复一次 | 显示已过期 |
| Run 取消 | Interaction/ToolCall/Block 同事务取消 | 卡片不可编辑 |
| Worker 重启 | 从 Checkpoint 恢复 | 无需重新回答 |
| WS 断开 | Event REST replay | 不重复投影 |
| 客户端工具 claim 失效 | 回到 pending 或超时 | 合格设备可重新 claim |

## 十、关键代码位置与变更范围

### 10.1 DeepTutor 参考

```text
DeepTutor-main/deeptutor/core/tool_protocol.py
DeepTutor-main/deeptutor/runtime/registry/tool_registry.py
DeepTutor-main/deeptutor/core/agentic/tool_dispatch.py
DeepTutor-main/deeptutor/agents/chat/agent_loop.py
DeepTutor-main/deeptutor/tools/ask_user.py
DeepTutor-main/deeptutor/core/stream_bus.py
```

### 10.2 SparkService

```text
chat_sync/
├── ai_models/tool.py
├── ai_runtime/protocols/tool_protocol.py
├── ai_runtime/agentic/loop.py
├── ai_runtime/tools/
│   ├── registry.py
│   ├── scoped_registry.py
│   ├── policy.py
│   ├── composition.py
│   ├── dispatcher.py
│   ├── executor.py
│   ├── ask_user_schema.py
│   └── adapters/ask_user.py
├── ai_services/
│   ├── pending_interaction_service.py
│   ├── tool_state_service.py
│   └── stream_writer.py
├── ai_tasks/run_tasks.py
├── ai_api/
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
└── contracts/canonical.py
```

### 10.3 Chat Web

```text
chat-web/
├── components/chat/blocks/TaskBlocks.tsx
├── components/chat/blocks/ToolBlocks.tsx
├── components/chat/blocks/registry.tsx
├── components/chat/turn/TurnTraceRow.tsx
├── components/chat/turn/ToolPresentationSlot.tsx
├── lib/event-reducer.ts
├── lib/tools/tool-activity-reducer.ts
├── lib/tools/tool-block-normalizer.ts
├── types/chat.ts
└── contracts/spark-chat-v1/
    ├── schemas/block.v1.schema.json
    └── schemas/pending_interaction.v1.schema.json
```

### 10.4 禁止范围

- 不创建第二套 Run、ToolCall、PendingInteraction 或 Event 表。
- 不让 Web 直接调用 Provider 或执行模型工具决策。
- 不修改任何移动客户端代码；移动端接入另开实现工单，但必须复用本契约。
- 不修改 AI config bootstrap、明文 `api_key`、Pro 权益和模型场景选择。
- 不在本工单引入写工具、MCP、exec、imagegen 或完整 HealthKit 客户端实现。

## 十一、实施拆分

| 子工单 | 内容 | 依赖 | 出口证据 |
|---|---|---|---|
| `CHAT-AI-029A` | Tool Manifest Entry 与 target 通用字段收敛 | 024 | Registry/Composition contract test |
| `CHAT-AI-029B` | Provider 前 target/platform/capability 过滤 | 029A | Provider request snapshot test |
| `CHAT-AI-029C` | PendingInteraction DTO v2 与回答归属校验 | 029A | API/JSON Schema contract test |
| `CHAT-AI-029D` | ask_user canonical toolQuestionCards 投影 | 029C | Block/Event fixture |
| `CHAT-WEB-029E` | Web AskUser 可交互卡片与刷新恢复 | 029C/D | Browser E2E/a11y |
| `CHAT-AI-029F` | 同 Run checkpoint/resume、过期与多设备竞争 | 029C/D | Celery/recovery integration test |
| `CHAT-AI-029G` | 安全投影、日志、监控与跨端 fixtures | 029A–F | Security/contract report |
| `CHAT-AI-029H` | DeepTutor 纯函数/协议迁移登记与适配层验收 | 029A–G | 来源、许可证、迁移矩阵和 parity report |

推荐顺序：先完成 `ask_user` 服务端暂停恢复和 Web 卡片，再开放一个只读 client tool 证明 target=client 主干，最后扩展其他客户端工具。

## 十二、测试矩阵

### 12.1 Tool Manifest

- server/client target 必填与非法值拒绝。
- Web Run 不向 Provider发送无执行器的 client tools。
- iOS capability 不满足时过滤 HealthKit 工具。
- target 不能被模型 arguments 覆盖。
- Registry 更新不改变已暂停 Run 的冻结 Manifest。
- Provider snapshot 中只有标准 function schemas。

### 12.2 AskUser

- 模型决定不调用工具时直接完成。
- 模型调用 ask_user 后 Run 进入 waiting。
- 1–4 题、单选、多选、自由文本。
- question ID 去重和非法回答拒绝。
- 回答恢复同一 run_id，不创建新 Run。
- checkpoint 中只追加一次 role=tool。
- 多标签页同答、异答竞争。
- Web 回答、iOS 查看；iOS 回答、Web 查看。
- Worker/Redis/WS 短暂中断后恢复。
- 过期、拒绝、取消和 Run 终态晚到回答。

### 12.3 卡片

- interaction.requested 生成一个 toolQuestionCards Block。
- pending/resolved/refused/expired/cancelled 更新同一 Block revision。
- live Event、REST replay、历史 Sync 得到相同 UI。
- 原始 arguments、ToolResult.content、Token 和健康原文不进入 DOM。
- 未知 Block kind 安全降级，不影响最终答案。
- 键盘操作、焦点、错误提示和屏幕阅读器标签通过。

### 12.4 工具执行

- Schema 第一层错误。
- Policy/权限/Context 第二层错误。
- timeout、retry、cancel、duplicate 和 max round。
- ToolResult content/metadata/sources/pause 四路不串线。
- 同一 tool_call_id 在 Worker 重试时最多执行一次。

## 十三、可观测性

建议指标：

- `chat_tool_manifest_total{target,tool,outcome}`。
- `chat_tool_filtered_total{target,reason,platform}`。
- `chat_tool_call_total{tool,target,status}`。
- `chat_tool_duration_seconds{tool,target}`。
- `chat_interaction_total{kind,status,tool}`。
- `chat_interaction_wait_seconds{kind}`。
- `chat_interaction_response_conflict_total{kind}`。
- `chat_interaction_resume_total{outcome}`。
- `chat_tool_projection_redaction_total{field}`。

必须能通过 request_id、run_id、tool_call_id、interaction_id 串联一次完整暂停/恢复，但不能依赖日志恢复事实状态。

## 十四、出口验收

- [ ] 工具调用决定权属于模型，服务端只提供经过策略过滤的 Tool Schema 并拥有最终执行权。
- [ ] target 是所有工具的统一必填字段，server/client 在 Provider 请求前完成隔离。
- [ ] Web 无合格移动执行器时，HealthKit/定位工具不会发送给模型。
- [ ] ask_user 暂停当前 Run，回答后恢复同一个 Run 和 Agent Loop。
- [ ] 每张问答卡携带 run_id、interaction_id、interaction_key、tool_call_id、question_ids、expires_at、schema_version。
- [ ] 用户回答经过 owner、状态、Schema、过期和幂等校验。
- [ ] Tool Schema 与 ToolPolicy 两层校验均有测试。
- [ ] ToolResult.content、metadata、sources、pause_for_user 分路正确。
- [ ] ask_user 使用 canonical toolQuestionCards，不再伪装为 searchSummary。
- [ ] Web 卡片支持选择、文本、提交、恢复、竞争、过期和取消。
- [ ] live、replay、历史 Sync 在所有客户端使用相同事实协议。
- [ ] 公开卡片不包含原始 arguments、健康原文、Token、内部堆栈和 Provider 请求。
- [ ] 没有创建第二套 Run/Tool/Event/Block 事实源。
- [ ] 没有修改移动客户端、AI bootstrap、明文 api_key、Pro 或模型选择。

---

工单结论：Spark 工具系统以模型自主 function calling 为入口，以服务端 Tool Manifest/Policy 为执行边界，以 `target` 完成 server/client 隔离，以持久化 PendingInteraction 实现 `ask_user` 和客户端工具暂停恢复，以 canonical Event/Block 为多客户端唯一展示事实源。首个完整交付必须是 `ask_user`：暂停同一个 Run、跨刷新恢复、回答后继续同一个 Agent Loop，并生成安全、可交互、可回放的 `toolQuestionCards`。
