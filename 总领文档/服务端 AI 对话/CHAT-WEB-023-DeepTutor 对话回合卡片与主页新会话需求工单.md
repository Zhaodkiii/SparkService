# CHAT-WEB-023 DeepTutor 对话回合卡片与主页新会话需求工单

创建日期：2026-08-25  
状态：待实现  
优先级：P0  
实施端：Spark Chat Web  
参考项目：DeepTutor Web 1.5.9 源码快照  
关联工单：`CHAT-WEB-017`、`CHAT-WEB-021`  
本次交付边界：只创建需求工单，不修改 Python、TypeScript、CSS、测试、配置、数据库迁移或客户端代码。

## 一、模块目标

本工单解决两个相互关联的 Web 对话体验问题：

1. 对话正文、思考状态、工具调用、工具结果卡片必须按 DeepTutor 的回合视觉与交互逻辑统一展示。
2. 用户点击侧边栏「主页」或品牌主页入口时，必须进入一个新的对话 Draft，而不是继续显示或发送到最近一条历史对话。

目标体验：

```text
点击「主页」
  → 处理当前 Run
  → 清空当前 Thread 选择
  → 进入 /home 新对话 Draft
  → 展示空对话与可用 Composer
  → 用户发送第一条消息
  → 创建并同步新的 Spark ChatThread
  → 在新 Thread 上创建 ChatRun
  → URL 替换为 /home/{thread_id}
  → 本轮按「活动 / 思考 / 工具 / 正文 / 工具卡片」统一渲染
```

本工单对齐 DeepTutor 的页面业务逻辑和视觉语法，但继续使用 SparkService 的 Auth、Thread、Message、Block、Run、Event、Preferences 和 Context，不引入 DeepTutor Session API、WebSocket 或数据模型。

## 二、DeepTutor 对话回合卡片与主页新会话模块结构

### 2.1 结构职责表

| 层级 | DeepTutor 参考职责 | Spark 当前职责 | 本工单目标 |
|---|---|---|---|
| 路由入口 | `/home/[[...sessionId]]` 根据 URL 新建或加载 Session | `/home/[[...threadId]]` 直接渲染 `ChatWorkspace` | 区分 `/home` 新 Draft 与 `/home/{threadId}` 历史 Thread |
| 主页导航 | Sidebar `handleNewChat()` 取消当前生成、`newSession()`、跳转 `/home` | 「主页」只是普通 Link | 主页点击成为明确的新对话命令 |
| 会话状态 | `UnifiedChatContext` 保存 draft key、sessionId、messages、stream | `ThreadContext` 保存 threads、selectedThreadId、messages | 增加 Web Draft 状态，禁止自动回退最近 Thread |
| 回合投影 | `AssistantActivity` 把状态、Trace、Tool 与正文组合 | `ChatMessages` 分离 Tool Block 与正文 | 建立统一 `TurnPresentation` 投影 |
| 思考展示 | `TracePanels`、`ModelThinkingCard` | `deepThought` 只读卡、`assistant.status` 文案 | 只展示公开思考摘要与阶段，不展示隐藏推理 |
| 工具轨迹 | tool call/result 按 call ID 归并为动态 Trace Row | `ActivityDisclosure` 聚合 `toolCall/toolResult` | 对齐运行中展开、结束后折叠与状态语义 |
| 工具结果卡 | 文件、图片、研究、测验等专用 Viewer/Card | iOS 36 kind Block Registry | 通用工具轨迹与业务结果卡分层，不重复展示 |
| 流式事实源 | Session Stream Event | Run Event + Block projection | 保留 `event-reducer` 幂等与 replay 语义 |

### 2.2 具体目录结构

以下路径均已在当前文件系统中核验存在；标注“建议新增”的文件当前不存在。

```text
DeepTutor-main/web/
├── app/(workspace)/home/[[...sessionId]]/page.tsx
├── context/UnifiedChatContext.tsx
├── components/sidebar/WorkspaceSidebar.tsx
├── components/chat/home/ChatMessages.tsx
├── components/chat/home/TracePanels.tsx
├── components/chat/home/SessionActivityPanel.tsx
└── components/common/ModelThinkingCard.tsx

SparkService/chat-web/
├── app/(workspace)/home/[[...threadId]]/page.tsx
├── components/sidebar/WorkspaceSidebar.tsx
├── components/chat/home/
│   ├── ChatWorkspace.tsx
│   ├── ChatMessages.tsx
│   ├── ChatBlockRenderer.tsx
│   ├── ActivityDisclosure.tsx
│   ├── ToolActivityDisclosure.tsx
│   ├── SessionActivityPanel.tsx
│   └── ChatComposer.tsx
├── components/chat/blocks/
│   ├── registry.tsx
│   ├── TextBlocks.tsx
│   ├── ToolBlocks.tsx
│   ├── CardsBlocks.tsx
│   ├── MediaBlocks.tsx
│   ├── VisualizationBlocks.tsx
│   ├── TaskBlocks.tsx
│   └── NoticeBlocks.tsx
├── context/
│   ├── ThreadContext.tsx
│   └── RunControlContext.tsx
├── lib/
│   ├── event-reducer.ts
│   ├── chat/activity-projection.ts
│   ├── tools/tool-activity-reducer.ts
│   └── tools/tool-activity-selectors.ts
├── types/
│   ├── chat.ts
│   └── tool.ts
└── tests/
    ├── components.test.tsx
    ├── event-reducer.test.ts
    └── tool-activity.test.ts

建议新增：
SparkService/chat-web/
├── components/chat/turn/
│   ├── AssistantTurn.tsx
│   ├── TurnActivity.tsx
│   ├── TurnTraceRow.tsx
│   ├── PublicThinkingCard.tsx
│   └── ToolPresentationSlot.tsx
├── lib/chat/
│   ├── turn-presentation.ts
│   └── turn-activity-projector.ts
└── tests/
    ├── turn-presentation.test.ts
    └── home-new-draft.test.tsx
```

### 2.3 目录职责与依赖方向

```text
Route / Sidebar command
  → ThreadContext 新会话状态机
  → RunControlContext 取消/解绑当前 Run
  → ChatComposer 首次发送编排
  → Spark Sync API + Run API
  → Run Event / Message Block
  → event-reducer
  → turn-activity-projector
  → AssistantTurn / Block Registry
```

- UI 组件不得直接调用 Thread、Run 或 Sync URL。
- `ThreadContext` 负责当前是 Draft 还是持久化 Thread。
- `RunControlContext` 负责 Run 生命周期和事件订阅，不负责页面导航。
- `event-reducer` 负责 wire event 的幂等、顺序与持久化投影。
- `turn-activity-projector` 负责将公开 Event/Block 转换为可展示的回合活动模型。
- `AssistantTurn` 只消费 ViewModel，不解析 Provider 原始报文。
- `Block Registry` 继续负责结构化业务结果卡，不复制工具活动状态机。

## 三、能力一：统一对话正文卡片

### 3.1 需求说明

用户消息与助手最终回答必须对齐 DeepTutor 的消息层级：用户消息是紧凑气泡，助手回答是开放式 Markdown 内容，不把整条回答包成厚重的大卡片。

助手正文来自 Spark `ChatMessageBlock.kind=text`，历史消息与流式消息必须使用同一渲染器。

### 3.2 基础要求与业务规则

1. 用户内容和助手内容必须按 Message/Block 归属渲染，不能把当前 Run 的全部 Block 重复渲染到每一条历史助手消息。
2. 正文按 `order_key`、`revision` 和稳定 Block ID 更新。
3. 流式 `block.delta` 只追加到目标 Block；刷新后从 Sync/Replay 得到相同内容。
4. Markdown 支持标题、段落、列表、引用、表格、代码块和安全链接。
5. HTML 必须经过现有 `sanitize-html`；不得渲染 script、事件属性、危险 URL。
6. 正文结束后显示复制、反馈、重新生成等操作；生成中不得把未完成文本当作终态。
7. 工具调用过程不得混入最终正文的复制结果。
8. 无正文但存在工具活动、等待交互或错误时，仍必须显示完整回合外壳。

### 3.3 主流程

```text
Message history + live Blocks
  → 按 message_id 归属
  → 按 Block ID 合并历史与 live revision
  → 按 order_key 排序
  → 分为 activity / final content / presentation card
  → AssistantTurn 渲染
  → 完成后显示 MessageActions
```

### 3.4 失败、重试和恢复

- 单个 Block 解析失败时只降级该 Block，不隐藏整条 Message。
- WebSocket 丢包后使用 Run Event replay；不得重置已显示正文。
- revision 倒退或重复 event 必须忽略。
- Markdown 渲染失败时显示纯文本安全降级。
- Regenerate 创建新的 Run/分支语义，不覆盖旧回答后伪装成原回答。

### 3.5 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat-web/components/chat/home/ChatMessages.tsx` | 拆出 Message/Turn 归属与 live 合并，停止在组件内临时拼接全部 Block |
| `chat-web/components/chat/turn/AssistantTurn.tsx` | 建议新增统一助手回合外壳 |
| `chat-web/components/chat/blocks/TextBlocks.tsx` | 保留安全 Markdown，补齐 streaming/empty/error 视觉 |
| `chat-web/lib/chat/turn-presentation.ts` | 建议新增纯函数，将 Blocks 分类为 activity/content/presentation |
| `chat-web/lib/event-reducer.ts` | 保留 sequence/revision 幂等，不增加视觉判断 |

### 3.6 验收标准

- 历史回答、实时回答与刷新后的回答视觉一致。
- 多条助手 Message 不会互相复用或重复显示 Block。
- 复制回答只包含最终用户可见正文。
- Markdown 表格、代码、链接和长文本无横向页面溢出。
- 单 Block 错误不会让整条消息白屏。

## 四、能力二：思考与回合活动卡片

### 4.1 需求说明

对齐 DeepTutor `AssistantActivity` 的交互语法：助手开始工作时，在最终回答上方显示一条轻量活动头；活动进行中默认展开，完成并进入最终回答阶段后自动折叠，用户手动展开/折叠后尊重其选择。

这里的“思考”是可公开展示的运行阶段、模型提供的公开 reasoning summary 或明确持久化为用户可见的 `deepThought` Block，不等于隐藏 Chain-of-Thought。

### 4.2 基础要求与业务规则

1. 不展示 Provider 原始 `reasoning_delta`、隐藏 prompt、系统消息或内部 scratchpad。
2. 没有公开思考内容时显示阶段状态，例如“正在思考”“正在查找资料”“正在组织回答”，不能编造推理文本。
3. 有安全的 `deepThought` Block 时允许在折叠体内以 Markdown 展示。
4. 运行中默认展开；进入 final answer 或 Run terminal 后默认折叠。
5. 用户手动切换后，本条 Message 生命周期内不再自动覆盖其选择。
6. 标题状态必须来自 Run/Event，不根据是否出现省略号猜测。
7. 回合耗时使用服务端 timestamp 或 Run started/finished 时间；不可用时不显示虚假耗时。
8. `prefers-reduced-motion` 下取消旋转以外的非必要过渡，并提供静态状态图标。

### 4.3 公开信息允许表

| 可展示 | 禁止展示 |
|---|---|
| `assistant.status` 的公开状态 | Provider 原始 reasoning token 文本 |
| 用户可见 `deepThought` Block | system prompt、developer prompt |
| 工具公开名称和脱敏动作摘要 | raw arguments、身份 ID、密钥、内部 URL |
| 工具公开结果预览和来源数量 | 完整健康记录原文、工具内部异常堆栈 |
| Run 阶段和可计算耗时 | 模型内部草稿和隐藏观察文本 |

### 4.4 状态模型

```text
idle
  → exploring       回合开始，Activity 展开
  → using_tools     存在运行中的工具 Row
  → composing       最终正文开始流式输出
  → completed       Activity 自动折叠

exploring/using_tools/composing
  → waiting         ask_user 或客户端工具等待
  → failed          展示失败状态，可按契约重试
  → cancelled       展示已停止
  → interrupted     保留已生成内容并标记中断
```

### 4.5 失败、重试和恢复

- 事件重放后必须恢复相同的活动状态、工具状态和默认折叠状态。
- 刷新页面后不恢复“用户手动展开”偏好，默认根据终态重新计算即可。
- 只有公开事件而没有内容 Block 时，仍展示活动状态。
- 未识别状态按“正在处理/处理完成”安全降级，并记录诊断日志。
- 失败不得把工具内部错误详情写入 DOM、日志或复制内容。

### 4.6 技术细节与设计代码位置

| DeepTutor 参考 | Spark 目标处理 |
|---|---|
| `components/chat/home/TracePanels.tsx::AssistantActivity` | 迁移折叠行为和视觉层级，重写事件投影 |
| `components/common/ModelThinkingCard.tsx` | 参考 streaming 展开、closed 折叠、user toggle 优先逻辑 |
| `components/chat/home/ChatMessages.tsx` | 参考 Activity 固定在最终正文之前的组合顺序 |
| `chat-web/components/chat/home/ActivityDisclosure.tsx` | 演进为 Turn 级 Activity，不只统计工具数量 |
| `chat-web/lib/chat/turn-activity-projector.ts` | 建议新增公开 allowlist 投影 |
| `chat-web/types/chat.ts` | 增加 `TurnActivityViewModel` 相关类型，不把 raw provider payload 暴露给 UI |

### 4.7 验收标准

- 生成中 Activity 默认展开并实时更新。
- 最终正文开始或 Run 完成后 Activity 自动折叠。
- 用户手动展开后不会因后续 delta 自动关闭。
- 没有公开 reasoning summary 时不显示虚构思考正文。
- 页面源代码、DOM、复制内容和前端日志中不存在隐藏 reasoning。

## 五、能力三：工具调用轨迹卡片

### 5.1 需求说明

工具调用轨迹用于回答“AI 正在做什么”，对应 DeepTutor Trace Row，不等于最终业务结果卡。每次工具调用必须在当前助手回合的 Activity 内形成一条稳定 Row。

### 5.2 基础要求与业务规则

1. 使用 `tool_call_id` 关联 requested、running、result、failed、cancelled。
2. 同一调用不得同时显示独立 toolCall 卡和 toolResult 卡。
3. 多工具按 `round_index`、`call_index`、`order_key` 稳定排序。
4. 运行中显示 spinner/进行态，成功显示完成态，失败和取消使用不同图标与文案。
5. Row 标题使用服务端 `display_name`；参数只显示 `display_args` 安全投影。
6. 结果只显示 `result_preview`、`source_refs` 数量和公开错误。
7. 多个 Tool Row 位于同一个回合 Activity 内，不生成多个互不关联的折叠容器。
8. 未知工具使用“服务工具”安全回退，不直接 title-case 内部工具名。
9. 工具 Feature Flag 关闭时，纯文本仍正常工作，未知工具块不得污染正文。

### 5.3 主流程

```text
tool.call.requested
  → 创建/更新 ToolActivityDTO
  → Activity 内新增稳定 Row

tool.call.started / block.updated
  → 同一 Row 进入 running

tool.result / tool.call.cancelled
  → 同一 Row 收敛为 completed/failed/cancelled
  → 若产生结构化展示 Block，交给 ToolPresentationSlot
```

### 5.4 失败、重试和恢复

- result 先于 requested 到达时，Reducer 必须能以 call ID 建立终态 Row。
- 重复 event 或 replay 不重复增加 Row。
- 工具超时与取消必须收敛，不能永久显示 spinner。
- 失败显示安全 `message_key` 映射；raw exception 只保留服务端受控日志。
- `duplicate_of` 显示“已复用相同请求结果”，但不重复展示结果卡。

### 5.5 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat-web/lib/tools/tool-activity-reducer.ts` | 保持以 call ID 幂等收敛，补齐乱序和 replay 测试 |
| `chat-web/lib/tools/tool-activity-selectors.ts` | 输出按 round/call 排序的 Turn Rows |
| `chat-web/lib/chat/activity-projection.ts` | 保留敏感字段过滤，增加动作文案与终态映射 |
| `chat-web/components/chat/home/ActivityDisclosure.tsx` | 从工具数量摘要升级为 DeepTutor 式状态头 + Trace Rows |
| `chat-web/components/chat/turn/TurnTraceRow.tsx` | 建议新增单 Row 展示组件 |
| `chat-web/components/chat/home/ToolActivityDisclosure.tsx` | 过渡期兼容；统一 Turn Activity 后不再重复渲染同一调用 |

### 5.6 验收标准

- 一个 `tool_call_id` 在 UI 中只有一条活动轨迹。
- requested → running → completed 状态原位更新，无跳行。
- 并行工具顺序稳定，刷新和 replay 后一致。
- 工具失败不会泄露参数、健康原文、URL、Key 或堆栈。
- Run 结束后不存在永久 spinner。

## 六、能力四：结构化工具结果卡片

### 6.1 需求说明

结构化工具结果卡回答“工具产出了什么”，必须与工具调用轨迹分层。Activity 中展示动作和状态；正文区域按 Block Registry 展示真正需要用户阅读或操作的内容。

典型结果包括：

- 图片、文件与附件。
- 知识库卡片、检索摘要与引用。
- 健康资料、结构化健康数据和风险提示。
- 饮食、运动、睡眠、步数、能量和天气可视化。
- 任务、问答、成员选择、授权和定位权限卡。
- `ask_user` 与客户端工具等待卡。

### 6.2 基础要求与业务规则

1. `toolCall/toolResult` 是活动轨迹；`tool` 或领域 Block 是结果展示，两者职责不可混用。
2. 同一工具结果如果已有领域 Block，不再额外显示通用结果卡。
3. 结果卡按原始 `order_key` 插入正文流，并保留 `parent_tool_call_id`、`parent_block_id`。
4. 平台专属能力在 Web 不可执行时显示明确只读/转到移动端状态，不能伪造成功。
5. 卡片必须使用 Spark/iOS 已冻结的 Block kind 和 payload contract，不采用 DeepTutor Quiz/Research 私有 DTO。
6. 未知 kind 显示安全 fallback，并上报 `block_kind_unsupported`。
7. 单卡必须有 Error Boundary。
8. 外链、HTML、附件 URL 和健康信息按现有安全策略处理。

### 6.3 展示优先级

| 数据情况 | Web 展示 |
|---|---|
| 有领域专用 Block | Activity Row + 专用结果卡 |
| 只有安全 `result_preview` | Activity Row 展开详情，不再生成正文卡 |
| 只有失败结果 | Activity Row 失败态；必要时显示回合错误提示 |
| Web 无平台能力 | Activity Row 完成/等待 + 平台限制卡 |
| 未知 Block kind | Activity 不受影响，结果位置显示安全兼容卡 |

### 6.4 失败、重试和恢复

- 结构化卡解析失败只影响该卡，工具活动仍显示终态。
- 附件签名 URL 失效时重新请求授权 URL，不把旧 URL 永久保存到 ViewModel。
- 等待卡刷新后从 PendingInteraction 恢复，不依赖 React 本地 state。
- 卡片提交动作必须有 interaction/version 幂等键。
- 已提交或被其他设备处理的卡片进入只读终态。

### 6.5 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat-web/components/chat/blocks/registry.tsx` | 保持 kind → renderer 唯一注册表 |
| `chat-web/components/chat/blocks/ToolBlocks.tsx` | 区分通用活动投影与 `tool` 展示 Block |
| `chat-web/components/chat/blocks/CardsBlocks.tsx` | 健康、知识、交互类结果卡 |
| `chat-web/components/chat/blocks/MediaBlocks.tsx` | 图片、文件、生成产物 |
| `chat-web/components/chat/blocks/VisualizationBlocks.tsx` | 图表与健康可视化 |
| `chat-web/components/chat/blocks/TaskBlocks.tsx` | 任务和计划类卡片 |
| `chat-web/components/chat/turn/ToolPresentationSlot.tsx` | 建议新增去重与位置编排层 |
| `chat-web/lib/chat/block-normalizer.ts` | 继续处理 iOS/Swift payload 归一化 |

### 6.6 验收标准

- 工具活动与结构化结果不重复。
- 所有当前已知 iOS Block kind 都有明确渲染或平台限制状态。
- 工具结果卡刷新、回放和跨端同步后位置一致。
- 单卡错误不影响正文、其他卡和 MessageActions。
- Web 不会执行 HealthKit、系统定位授权等移动端专属动作。

## 七、能力五：点击主页创建新的对话

### 7.1 需求说明

侧边栏「主页」和品牌主页入口不再只是导航到当前对话工作区，而是一个明确的“开始新对话”命令。

无论用户当前位于：

- `/home/{thread_id}` 历史对话。
- `/medical`、`/nutrition`、`/exercise` 等工作区。
- `/home` 新对话 Draft。

点击主页后都进入 `/home`。如果当前不是空白 Draft，则重置为一个新的 Draft，不自动选择最近 Thread，不把下一条消息发送到历史 Thread。

### 7.2 与 DeepTutor 的对齐事实

DeepTutor 当前实现：

```text
WorkspaceSidebar.handleNewChat()
  → cancelStreamingTurn()
  → newSession()
  → router.push("/home")

/home page mount without sessionId
  → newSession()

server returns sessionId after first message
  → router.replace(`/home/${sessionId}`)
```

Spark Web 目标语义：

```text
handleHomeNewChat()
  → settleActiveRun()
  → ThreadContext.startNewDraft()
  → router.push("/home")

first send from draft
  → materializeDraftThread()
  → sync push new ChatThread
  → create ChatRun(thread_id)
  → router.replace(`/home/${thread_id}`)
```

### 7.3 基础要求与业务规则

1. `/home/{thread_id}` 表示打开指定历史对话。
2. `/home` 表示新对话 Draft，不能在 Thread 加载完成后自动选中最近 Thread。
3. 点击主页时不得立即产生大量空 ChatThread；与 DeepTutor 一样，首条消息发送时再物化服务端 Thread。
4. 新 Draft 使用浏览器内稳定 `draft_id`，用于同一页面生命周期的 single-flight 和日志关联。
5. Draft 不进入“最近对话”，没有用户消息的 Draft 不同步到 iOS。
6. 首次发送成功创建 Thread 后，用 `router.replace` 把 `/home` 替换为 `/home/{thread_id}`，避免浏览器后退回到已消费 Draft。
7. 创建 Thread 成功但创建 Run 失败时保留该 Thread、输入文本和失败提示，重试不得再建第二个 Thread。
8. Thread push 失败时不创建 Run，不清空输入，不把 Draft 标记为已物化。
9. 多次点击主页时，如果已经是未输入、未物化、无附件/引用的空 Draft，保持当前 Draft，避免无意义重置。
10. Draft 有输入、附件或一次性引用时再次点击主页，需要提示用户确认放弃；确认后清理 Draft，取消则停留当前页。
11. 最近对话列表继续存在，点击历史项只加载该 Thread，不创建新对话。
12. 不恢复 CHAT-WEB-021 中“发送时优先选择最近 Thread”的行为。

### 7.4 当前 Run 处理规则

DeepTutor 会先调用 `cancelStreamingTurn()`。Spark 需要把该行为落到可确认的 Run 状态机：

| 当前状态 | 点击主页处理 |
|---|---|
| 无 Run/终态 Run | 立即进入新 Draft |
| queued/running | 发起取消并显示“正在停止当前回答”；收到取消终态后进入 Draft |
| waiting_for_user_input | 取消 PendingInteraction 后进入 Draft |
| waiting_for_client_tool | 取消等待；迟到结果必须被旧 Run 拒绝 |
| 取消失败/超时 | 停留原 Thread，显示错误；不得静默遗留后台 Run |

不得在旧 Run 仍处于非终态时直接把全局 Run 订阅切到新 Thread。若未来支持每 Thread 独立后台 Run，应另建多 Run 管理工单。

### 7.5 新 Draft 状态模型

```text
none
  → starting          用户点击主页
  → draft             新对话空态，可输入
  → dirty             存在文本/附件/引用
  → materializing     首次发送，创建 ChatThread
  → materialized      获得 thread_id
  → submitting        创建 ChatRun
  → active            URL=/home/{thread_id}

starting
  → blocked           旧 Run 取消失败

materializing/submitting
  → failed            保留 Draft 或已创建 Thread及输入
  → retrying          用户重试，复用 draft_id/thread_id/idempotency key
```

### 7.6 并发、幂等与恢复

- `materializeDraftThread()` 使用 Promise single-flight。
- `draft_id → thread_id` 映射在当前标签页内稳定；双击发送不能创建两个 Thread。
- Thread push 与 Run create 使用不同但稳定的幂等键。
- 如果页面在 Thread push 成功后、Run create 前刷新，应能从本地 pending mapping 或 Thread pull 找回 Thread。
- 多标签页各自的新 Draft 相互独立；真正创建的 Thread 通过 Sync 正常汇合。
- 浏览器前进/后退必须以 URL 为准：`/home/{id}` 加载历史，`/home` 新建/恢复当前空 Draft。
- 账号切换或退出登录必须清理 draft_id、输入、附件、引用和 pending mapping。

### 7.7 核心代码轮廓

以下仅为后续实现边界，不代表本次已写入代码：

```ts
type NewChatDraft = {
  id: string;
  status: "draft" | "dirty" | "materializing" | "materialized" | "failed";
  threadId: string | null;
};

async function startNewDraft(): Promise<boolean> {
  if (!(await settleActiveRun())) return false;
  clearSelectedThread();
  resetRunProjection();
  resetTurnContextDraft();
  createLocalDraftOnce();
  router.push("/home");
  return true;
}

async function ensureDraftThread(): Promise<string> {
  if (draft.threadId) return draft.threadId;
  return singleFlight(draft.id, async () => {
    const thread = buildNewThreadDTO(draft.id);
    await syncApi.pushThreads([thread]);
    bindDraftToThread(draft.id, thread.thread_id);
    return thread.thread_id;
  });
}

async function submitDraft(content: string): Promise<void> {
  const threadId = await ensureDraftThread();
  const accepted = await runApi.create(threadId, content, stableRunIdempotencyKey());
  if (accepted) router.replace(`/home/${encodeURIComponent(threadId)}`);
}
```

### 7.8 技术细节与设计代码位置

| 文件 | 改动方向 |
|---|---|
| `chat-web/components/sidebar/WorkspaceSidebar.tsx` | 将主页与品牌点击接入 `handleHomeNewChat`，不再只是普通 `/home` Link |
| `chat-web/app/(workspace)/home/[[...threadId]]/page.tsx` | 根据 URL 明确调用 open history 或 start/keep new Draft |
| `chat-web/context/ThreadContext.tsx` | 新增 Draft 状态与 `startNewDraft/materializeDraftThread`；删除 `/home` 自动选最近 Thread |
| `chat-web/context/RunControlContext.tsx` | 暴露 `settleActiveRun/resetProjectionForNewDraft`，等待取消终态 |
| `chat-web/components/chat/home/ChatComposer.tsx` | 首次发送只物化当前 Draft，不调用“复用最近 Thread”的 ensure 逻辑 |
| `chat-web/context/ChatContextProvider.tsx` | 新 Draft 隔离一次性引用；粘性 Preferences 按产品规则继承 |
| `chat-web/components/chat/home/ChatHeader.tsx` | Draft 固定显示“新对话”，物化前禁用重命名 |
| `chat-web/tests/home-new-draft.test.tsx` | 新增导航、脏 Draft、Run 取消、single-flight 和历史选择测试 |

### 7.9 验收标准

- 从任意历史 Thread 点击主页后看到空的新对话页。
- 新 Draft 的首条消息永远不会发往最近历史 Thread。
- 只点击主页、不发送消息，不产生服务端空 Thread。
- 首次发送只创建一个 Thread 和一个 Run。
- URL 在 Thread 创建后变为 `/home/{thread_id}`。
- 创建 Run 失败时用户输入不丢失，重试不重复创建 Thread。
- 旧 Run 非终态时必须先完成取消；失败则不切页。
- 点击最近对话仍能正常打开指定历史 Thread。

## 八、整体业务流程

### 8.1 新对话与首轮生成

```text
用户点击主页
  ↓
检查当前 Draft 是否有未保存内容
  ├─ 有 → 用户确认放弃
  └─ 无 → 继续
  ↓
检查当前 Run
  ├─ 非终态 → Cancel → 等待 terminal
  ├─ 取消失败 → 留在原 Thread
  └─ 已终态 → 继续
  ↓
创建本地 Draft，selectedThreadId=null
  ↓
router.push('/home')
  ↓
用户输入并发送
  ↓
single-flight 创建 ChatThread + sync push
  ↓
创建 ChatRun
  ├─ 失败 → 保留 Thread、输入与重试入口
  └─ 成功 → router.replace('/home/{thread_id}')
  ↓
Run Event → TurnProjection → 卡片流式展示
  ↓
Run terminal → Activity 折叠，正文与结果卡保留
```

### 8.2 历史对话打开

```text
点击最近对话
  → router.push('/home/{thread_id}')
  → Thread pull/message pull
  → active-run 查询 + event replay
  → TurnPresentation 重建
  → 展示与实时生成相同的卡片结构
```

### 8.3 回合卡片组合顺序

```text
Assistant Turn
├── Activity Header
│   ├── Public Thinking/Status Row
│   ├── Tool Call Row 1
│   ├── Tool Call Row 2
│   └── Public Observation/Summary（存在时）
├── Final Content Blocks
├── Tool Presentation / Domain Cards
├── Waiting Interaction Card（存在时）
├── Error / Interrupted Notice（存在时）
└── Message Actions + Usage（允许展示时）
```

通用工具调用与结果在 Activity 内归并；只有对用户有持续阅读或交互价值的领域结果才进入正文卡片区。

## 九、状态模型

### 9.1 页面状态

| 状态 | URL | selectedThreadId | 用户可见内容 |
|---|---|---|---|
| 新 Draft | `/home` | `null` | 空态、Composer、继承的粘性设置 |
| Draft 物化中 | `/home` | `null` | 保留输入，发送按钮忙碌 |
| Thread 已创建 | `/home/{id}` | `{id}` | 用户消息与 Run 状态 |
| 历史加载中 | `/home/{id}` | `{id}` | skeleton/缓存内容 |
| 历史就绪 | `/home/{id}` | `{id}` | 历史 Message 与卡片 |
| 切换受阻 | 原 URL | 原 ID | 取消失败提示，原 Run 继续可见 |

### 9.2 卡片状态

| 卡片 | pending | streaming/running | ready/completed | failed/cancelled |
|---|---|---|---|---|
| 正文 | 占位 | delta + cursor | Markdown | 保留部分内容 + 状态 |
| 思考/Activity | 状态头 | 默认展开 | 默认折叠 | 可展开查看公开摘要 |
| 工具 Row | requested | spinner + 动作 | check + 摘要 | error/cancel 图标 + 安全文案 |
| 结果卡 | skeleton/等待 | 渐进更新（契约支持时） | 完整卡片 | 局部错误卡 |

## 十、数据与持久化

### 10.1 服务端事实源

| 数据 | 事实源 |
|---|---|
| 对话身份 | `ChatThread.thread_id` |
| 消息 | `ChatMessage` |
| 正文与结构化卡 | `ChatMessageBlock` |
| 一轮生成 | `ChatRun` |
| 流式与工具活动 | `RunEvent` + Tool public projection |
| 工具调用状态 | `ChatToolCall` |
| 等待交互 | `PendingInteraction` |

### 10.2 Web 本地状态

Web 仅保存：

- 当前未物化 `draft_id`。
- Composer 文本、附件和一次性引用 Draft。
- Activity 的手动展开状态。
- Thread 创建 single-flight 和幂等键。

Web 不得把本地活动投影当成跨设备事实源。刷新后必须由 Message/Block/Event 重建。

### 10.3 粘性与一次性上下文

- 模型、角色、知识库等粘性偏好是否跨新对话继承，以现有 Preferences 契约为准。
- 文件、单回合引用、临时健康资源和未发送文本属于一次性 Draft。
- 点击主页创建新 Draft 时，一次性内容默认清空；有内容必须确认。
- 账号退出或切换时全部清理，不得跨账号恢复。

## 十一、错误模型

| 场景 | 用户处理 | 数据处理 |
|---|---|---|
| 旧 Run 取消失败 | 留在原对话，显示重试 | 不清 Thread/Run 投影 |
| Thread push 失败 | 保留 Draft 和输入 | 不创建 Run |
| Thread 成功、Run 失败 | 显示发送失败，可重试 | 复用已创建 Thread |
| 路由 Thread 不存在/无权 | 显示不可访问并允许回主页新建 | 不自动选最近 Thread |
| Event 缺口 | 显示恢复中 | REST replay 后收敛 |
| Tool event 乱序 | 不闪出重复 Row | call ID/revision 幂等归并 |
| Block 不支持 | 单卡安全降级 | 保留 raw wire，不影响其他卡 |
| 公开思考缺失 | 只显示阶段 | 不展示 raw reasoning |
| 工具失败 | Activity 失败态 | 结果卡按契约局部失败 |

## 十二、与其他模块的接口边界

### 12.1 本工单负责

- Web 主页新 Draft 状态与路由行为。
- 首条消息物化 Thread 的编排与幂等。
- 回合 Activity、思考、工具轨迹、正文和结果卡的展示编排。
- 历史、实时、Replay 的同构渲染。
- 卡片安全投影、错误隔离和可访问性。

### 12.2 本工单不负责

- 不修改 iOS、Android 或 HarmonyOS 客户端。
- 不修改 Apple/手机登录与会话隔离。
- 不修改 `bootstrap`、Pro、模型选择或明文 `api_key` 契约。
- 不新增 Provider、服务端工具或健康数据权限。
- 不展示隐藏 Chain-of-Thought。
- 不复制 DeepTutor 教学业务、Session API、Trace Event 或品牌资产。
- 不删除现有历史 Thread。

### 12.3 上下游接口

| 方向 | 模块 | 接口 |
|---|---|---|
| 上游 | Workspace Sidebar | `startNewDraft()` |
| 上游 | Recent Threads | `selectThread(threadId)` |
| 上游 | Composer | `materializeDraftThread()` + `createRun()` |
| 下游 | Chat Sync | thread push/pull、message pull |
| 下游 | Run Control | create/cancel/get active/events |
| 下游 | Event Reducer | event → runtime state |
| 下游 | Block Registry | canonical Block → Card |

## 十三、关键代码对应关系

### 13.1 DeepTutor 参考边界

| DeepTutor 文件 | 可对齐内容 | 不可直接迁移内容 |
|---|---|---|
| `web/components/sidebar/WorkspaceSidebar.tsx` | cancel → new draft → `/home` 的命令顺序 | Session API、翻译键和账号菜单 |
| `web/app/(workspace)/home/[[...sessionId]]/page.tsx` | URL 无 ID 新 Draft、有 ID 加载历史、服务端 ID 后 replace | Capability、KB、Agent、Quiz/Research 页面状态 |
| `web/context/UnifiedChatContext.tsx` | draft key、runner 隔离、new/load session 语义 | UnifiedWSClient 和 DeepTutor Event contract |
| `web/components/chat/home/ChatMessages.tsx` | Activity 在最终正文之前的组合顺序 | DeepTutor Message DTO 和专项能力 |
| `web/components/chat/home/TracePanels.tsx` | 活动头、自动折叠、Row 层级和状态语法 | raw Trace 解析、reasoning 内容和工具参数 |
| `web/components/common/ModelThinkingCard.tsx` | streaming 展开、完成折叠、手动选择优先 | `<think>` 原文展示逻辑 |

### 13.2 Spark 改动清单

| 优先级 | 文件 | 核心改动 |
|---|---|---|
| P0 | `chat-web/context/ThreadContext.tsx` | Draft/Thread 双状态；删除 `/home` 自动选最近 |
| P0 | `chat-web/components/sidebar/WorkspaceSidebar.tsx` | 主页点击触发新对话 command |
| P0 | `chat-web/components/chat/home/ChatComposer.tsx` | Draft 首次发送物化新 Thread |
| P0 | `chat-web/context/RunControlContext.tsx` | 当前 Run 取消完成后才允许切 Draft |
| P0 | `chat-web/lib/chat/turn-presentation.ts` | 统一回合分组、排序、去重 |
| P0 | `chat-web/lib/chat/turn-activity-projector.ts` | 公开 Activity/Thinking/Tool 投影 |
| P0 | `chat-web/components/chat/turn/AssistantTurn.tsx` | 回合统一渲染 |
| P1 | `chat-web/components/chat/home/ActivityDisclosure.tsx` | DeepTutor 式展开/折叠活动区 |
| P1 | `chat-web/components/chat/blocks/registry.tsx` | 结果卡插槽和去重边界 |
| P1 | `chat-web/app/globals.css` | Activity、Trace、Card 与响应式样式 |
| P1 | `chat-web/tests/home-new-draft.test.tsx` | 新 Draft 状态机 |
| P1 | `chat-web/tests/turn-presentation.test.ts` | 卡片组合与敏感字段测试 |

## 十四、测试策略

### 14.1 单元测试

1. `TurnPresentation` 把 text、deepThought、toolCall、toolResult、领域 Block 正确分类。
2. 同一 tool call/result 只生成一条 Tool Row。
3. 有领域结果 Block 时不生成重复通用结果卡。
4. Block 按 order/revision 稳定合并。
5. hidden reasoning/raw args/raw result 被 public projector 丢弃。
6. Activity 运行中展开、终态折叠、user toggle 优先。
7. `startNewDraft()` 不复用最近 Thread。
8. `materializeDraftThread()` 并发调用只创建一次。

### 14.2 组件测试

- 纯文本回合。
- 公开思考摘要 + 正文。
- 单工具成功、失败、取消。
- 两个并行工具。
- 工具活动 + 结构化健康卡。
- 只有工具无正文。
- interrupted 保留部分正文。
- 未知 Block 单卡降级。
- 当前历史 Thread 点击主页进入空 Draft。
- 脏 Draft 点击主页出现确认。

### 14.3 E2E

1. 登录后点击主页，URL 为 `/home`，显示空新对话。
2. 首次发送创建新 Thread，URL 变为 `/home/{id}`。
3. 最近列表出现新 Thread，历史 Thread 保持不变。
4. 双击发送只创建一条 Thread/Run。
5. Run 进行中点击主页，取消成功后进入 Draft。
6. 取消失败时仍停留原 Thread。
7. 工具运行中 Activity 展开，终态后折叠。
8. 刷新后工具轨迹、正文和结果卡不重复、不丢失。
9. iOS 同步来的结构化卡仍通过 Block Registry 正常展示。
10. 多标签页新建对话互不覆盖。

### 14.4 视觉与无障碍验收

- 桌面、平板、手机分别截取空 Draft、思考中、工具中、完成、失败五类基线。
- Activity header、Trace Row、正文与结果卡的缩进和间距与 DeepTutor 参考语法一致。
- disclosure 使用真实 button、`aria-expanded` 和受控内容 ID。
- 状态不能只依赖颜色；spinner 具有可读状态文本。
- 键盘可以展开 Activity、打开结果卡和回到 Composer。
- 屏幕阅读器不会逐字符朗读 streaming delta；使用节流后的 live region。
- reduced motion 下无强制旋转、位移或折叠动画。

## 十五、当前实现、缺口与演进

### 15.1 当前实现

- `types/chat.ts` 已包含 iOS 36 kind 和 Web 内部 `toolCall/toolResult`。
- `event-reducer.ts` 已支持 Run、Block、Tool Event 的基础投影和 replay 缺口标记。
- `ActivityDisclosure.tsx` 已能把 tool call/result 聚合为 Turn 级折叠区。
- `Block Registry` 已覆盖 text、deepThought、tool 和多类 iOS 结构化卡。
- `ThreadContext` 已存在 `createThread()` 与 `ensureActiveThreadForSend()`。
- `/home/[[...threadId]]` 和历史 Thread 深链接已存在。

### 15.2 当前缺口

- `/home` 加载完成后会自动选择最近 Thread，不代表新对话 Draft。
- `ensureActiveThreadForSend()` 会优先复用最近 Thread，与本工单目标冲突。
- 主页 Link 没有执行取消旧 Run 和创建 Draft 的业务命令。
- `ChatMessages` 仍在组件内临时合并历史/Live Blocks，回合归属边界不够稳定。
- Activity 主要围绕工具数量，缺少 DeepTutor 式完整回合阶段与公开思考行。
- `deepThought` 与 Activity 是两套独立视觉，没有统一折叠策略。
- 通用工具结果和领域结果卡存在重复展示风险。
- 当前未发现独立的 `turn-presentation` 纯函数测试。

### 15.3 建议实施阶段

#### CHAT-WEB-023A：契约与投影基线

- 冻结公开 Activity 字段 allowlist。
- 建立 `TurnPresentation`、fixture 和敏感字段测试。
- 明确 `toolCall/toolResult` 与领域 Block 去重规则。

#### CHAT-WEB-023B：回合卡片重构

- 新增 `AssistantTurn`、`TurnActivity`、`TurnTraceRow`。
- 对齐 DeepTutor 自动折叠和手动选择优先逻辑。
- 历史与 Live 使用同一投影。

#### CHAT-WEB-023C：主页新 Draft 状态机

- `ThreadContext` 增加 Draft 状态。
- 主页/品牌入口接入新对话命令。
- 首条发送物化 Thread，移除最近 Thread fallback。

#### CHAT-WEB-023D：Run 切换与恢复

- 非终态 Run 先取消并等待终态。
- Thread 成功、Run 失败的恢复与幂等。
- Back/Forward、多标签和账号切换测试。

#### CHAT-WEB-023E：视觉、安全与上线门禁

- Desktop/Tablet/Mobile 回归。
- hidden reasoning/raw tool data 泄露测试。
- Feature Flag 灰度与指标监控。

## 十六、发布与回滚

### 16.1 发布顺序

1. 先上线纯函数投影和测试，不改变 UI。
2. 灰度新的 Turn 卡片渲染器。
3. 验证历史、Live 和 Replay 一致后启用主页新 Draft。
4. 验证取消旧 Run 与首发物化。
5. 最后删除旧的最近 Thread fallback 和重复 Tool disclosure。

### 16.2 Feature Flag

建议拆分：

```text
NEXT_PUBLIC_CHAT_TURN_CARDS_V2
NEXT_PUBLIC_CHAT_HOME_NEW_DRAFT
```

- 卡片开关可独立回滚至现有 Renderer。
- 新 Draft 开关可回滚页面命令，但不得删除已创建 Thread。
- 回滚不改变 Message/Block/Event wire contract。

### 16.3 观测指标

```text
chat_home_new_draft_total{outcome}
chat_home_active_run_cancel_total{outcome}
chat_draft_materialize_total{outcome}
chat_draft_duplicate_thread_total
chat_turn_projection_fallback_total{kind}
chat_tool_activity_duplicate_total
chat_public_thinking_block_total{source}
chat_sensitive_projection_rejected_total{field}
```

## 十七、整体验收标准

- [ ] 点击主页或品牌主页入口进入新的空白对话 Draft。
- [ ] `/home` 不自动选择最近历史 Thread。
- [ ] `/home/{thread_id}` 正常打开指定历史 Thread。
- [ ] 只点击主页不会创建服务端空 Thread。
- [ ] 首次发送只创建一个 Thread 和一个 Run。
- [ ] Run 创建失败不丢输入、不重复创建 Thread。
- [ ] 非终态 Run 完成取消前不会切换到新 Draft。
- [ ] 对话正文、思考、工具轨迹和工具结果卡具有统一回合层级。
- [ ] Activity 运行中展开、完成后折叠，手动选择优先。
- [ ] 同一工具调用只显示一条 Activity Row。
- [ ] 通用工具结果与领域结果卡不重复。
- [ ] 历史、实时和 Replay 后的卡片顺序及状态一致。
- [ ] 已知 iOS Block 继续正常展示。
- [ ] 未知 Block 只局部降级。
- [ ] 不展示隐藏 Chain-of-Thought、raw arguments、raw result、Key、内部 URL 或健康原文。
- [ ] 不修改 iOS、Android、HarmonyOS、登录、bootstrap、Pro 或模型 Key 契约。
- [ ] 桌面、平板、移动端和无障碍测试通过。

## 十八、与既有工单的优先级

本工单是 `CHAT-WEB-017` 的回合卡片与主页会话行为细化工单。

本工单对 `CHAT-WEB-021` 的主页行为作出新的产品决策：

```text
CHAT-WEB-021 旧规则：/home 默认最近 Thread，首次发送可复用最近 Thread。
CHAT-WEB-023 新规则：/home 永远代表新 Draft，首次发送必须物化新的 Thread。
```

发生冲突时，以本工单的主页新 Draft 规则为准；`CHAT-WEB-021` 中消息模型对齐、Run 恢复和安全要求继续有效。

## 十九、最终结论

本需求不是简单增加几张独立卡片，而是建立完整的助手回合展示模型：公开活动和思考位于回合顶部，工具调用按 call ID 归并为轨迹，最终回答保持开放式正文，真正对用户有价值的工具产物通过 Block Registry 作为结构化结果卡展示。

主页也不再等价于“回到最近一次聊天”。对齐 DeepTutor 后，点击主页意味着开始一个新的本地 Draft；用户第一次发送时才创建 Spark ChatThread，并在服务端返回 Thread 身份后切换到 `/home/{thread_id}`。这样既满足“进入主页就是新的对话”，也避免产生未发送内容的空会话记录。
