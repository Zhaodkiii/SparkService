# CHAT-WEB-021 Web 对话发送、iOS 消息卡片兼容与主页入口优化工单

创建日期：2026-08-25  
状态：待实现  
优先级：P0  
阶段归属：Web 对话主链路与跨端消息展示  
关联模块：`chat_sync`、`chat-web`、`ai_config`、Celery/Redis/Channels、iOS Chat Domain  
参考模型：`LookHealthClient/SparkClient/.../ChatMessage.swift` 第 1–1185 行  
工单性质：新建独立需求工单  
本次交付边界：只新增本 Markdown 工单，不修改任何 Python、TypeScript、Swift、配置、数据库迁移或部署文件。

## 一、工单目标

本工单同时解决三个直接影响 Chat Web 可用性的问题：

1. Web 已能创建 Run 请求，但服务端返回 `50392/chat_server_runs_disabled`，用户无法发送对话。
2. Web 消息模型和渲染器只实际支持文本与部分工具块，无法正常展示 iOS 上传到同一 `chat_sync` 会话中的结构化卡片。
3. Web 仍暴露“新建对话”和“搜索对话”，且没有选中 Thread 时禁止发送，与“主页就是对话入口”的产品目标冲突。

最终用户体验：

```text
登录 Web
  → 直接进入 /home 对话主页
  → 无需点击“新建对话”
  → 输入内容并发送
  → 服务端创建、排队和执行 Run
  → Web 流式展示回答
  → iOS 同一会话中的文本、附件、健康、任务、工具和风险卡片可正常展示
```

## 二、当前问题与根因

### 2.1 Web 无法发送对话

用户提供的请求：

```http
POST /api/v1/ai/chat/threads/631caca0-8675-4497-b0d6-73d3856461a3/runs/
HTTP 503

{
  "code": 50392,
  "msg": "chat_server_runs_disabled",
  "data": {
    "retryable": false,
    "request_id": "dc0747e0-c05a-43c6-958c-2f588bf9f770"
  }
}
```

Web 层正确将该错误映射为：

```text
服务端对话尚未开启，请联系管理员。
```

当前响应对应的服务端调用链：

```text
ChatComposer.submit
  → RunControlContext.createRun
  → SparkRunApi.create
  → POST /api/v1/ai/chat/threads/{thread_id}/runs/
  → CreateRunView.post
  → RunService.create_run
  → RunService._ensure_enabled
  → 运行进程读取到 CHAT_AI_SERVER_RUNS_ENABLED 为关闭态
  → 50392/chat_server_runs_disabled
```

代码事实：

```python
# SparkService/settings.py
CHAT_AI_SERVER_RUNS_ENABLED = os.getenv(
    "CHAT_AI_SERVER_RUNS_ENABLED",
    "false",
)
```

```python
# chat_sync/ai_services/run_service.py
if not settings.CHAT_AI_SERVER_RUNS_ENABLED:
    raise APIError(
        "chat_server_runs_disabled",
        code=50392,
        status_code=503,
        details={"retryable": False},
    )
```

已知部署基线：`CHAT_AI_SERVER_RUNS_ENABLED` 已配置完成，本工单不提出开启、关闭、修改默认值或重新配置该开关的方案。

结论：请求已通过认证、URL、Thread 和 BFF 转发；50392 表明处理该请求的实际 Django 进程读取到的运行态与已完成的配置不一致。后续应定位配置是否被目标进程加载、进程是否完成重载、请求是否命中另一套实例，以及运行链路是否具备执行条件，而不是再次修改该开关。

### 2.2 Run 开关已配置，仍需核对实际运行链路

当前执行器配置也默认为：

```text
CHAT_AI_RUN_EXECUTOR=disabled
```

`RunService._enqueue_run()` 只在 executor 为 `mock` 或 `provider` 时投递 Celery 任务。即使已完成 Run 开关配置，如果实际 executor 仍为 `disabled`，Run 也可能永久停在 `queued`，用户仍然得不到回答。因此本工单把后续排查集中在以下条件：

- executor 为 `provider`。
- `chat.ai` Celery Worker 存活并消费正确队列。
- Redis/Broker 可用。
- `chat.events` Outbox 可投递或可由 Beat 补偿。
- `AIScenarioModelBinding(chat)` 有一条活跃文本模型。
- 对应 `AIProviderKeyConfig` 含有效 endpoint 和 key。
- 生产 endpoint 使用 HTTPS，服务器可出站访问。
- Run/Event/Context/Usage/Outbox 迁移已执行。

### 2.3 Web 消息卡片不兼容 iOS

iOS `ChatMessage.swift` 将消息建模为：

```text
ChatMessage
├── id
├── threadId
├── role
├── blocks[]
├── clientMessageId / serverMessageId
├── deliveryState
├── createdAt / serverUpdatedAt
├── isTombstone
├── modelName
└── usageSummary

ChatMessageBlock
├── id
├── anchor
├── toolCallId / parentToolCallId / parentBlockId
├── nodeRole
├── payload
├── status
├── revision
├── orderKey
└── createdAt / updatedAt
```

Web 目前的 `ChatBlockDTO.payload` 只是 `Record<string, unknown>`，`ChatBlockRenderer` 仅明确处理：

```text
text
toolCall
toolResult
```

其他 Block 统一显示：

```text
结构化内容
此内容需要更新版本查看
```

更关键的是，iOS `Codable` 关联值的 wire payload 可能为：

```json
{
  "kind": "taskCards",
  "payload": {
    "task_cards": {
      "_0": []
    }
  }
}
```

而 Web 渲染器假定的文本形状是：

```json
{
  "payload": {
    "text": "..."
  }
}
```

当前 `normalizeSyncBlock()` 只把顶层元数据与 `payload` 分开，没有解析 Swift enum 的 `snake_case + _0` 关联值包装。所以“类型名存在”不等于“Web 可正常展示”。

### 2.4 主页仍要求显式建立对话

当前 `WorkspaceSidebar` 包含：

```text
新建对话按钮
搜索对话输入框
最近对话列表
```

`ChatComposer` 在没有 `selectedThreadId` 时禁用发送，并显示：

```text
请先新建或选择一个对话
```

当前 `ThreadContext` 只有显式 `createThread()` 可以解决空账号没有 Thread 的问题。这与目标冲突：用户进入主页后应立即输入和发送，不需要理解 Thread 概念。

## 三、范围与非范围

### 3.1 本工单后续实现范围

1. 完成纯文本 Provider Run 的生产开启、就绪检查、失败恢复和运维门禁。
2. 保持 Run 的幂等、单活、排队、流式、取消、回放和终态语义。
3. Web 消息领域模型对齐 iOS `ChatMessage`/`ChatMessageBlock`。
4. Web 支持 iOS 定义的全部 36 种 `ChatMessageBlockKind` 的可识别展示。
5. 建立 Swift wire payload 到 Web 视图模型的无损归一化适配层。
6. 移除 Web 中面向用户的“新建对话”和“搜索对话”入口。
7. `/home` 作为登录后唯一默认对话入口。
8. 空账号首次发送时由系统幂等地准备 Thread，不暴露“新建”步骤。

### 3.2 明确不包含

- 本次不修改任何 iOS 客户端代码。
- 不改变 iOS 现有 `ChatMessage.swift`、CoreData、Sync DTO 和渲染流程。
- 不修改 Android 或 HarmonyOS 客户端。
- 不实现对话搜索。
- 不保留 Web “新建对话”按钮。
- 不要求用户在首次发送前选择 Thread。
- 不删除服务端 Thread 数据模型；Thread 仍是 Message/Run/Preferences 的必要内部容器。
- 不强制 Web 执行 HealthKit、系统定位授权、相机或 iOS Settings 跳转等平台专属动作。
- 不把不支持的平台动作伪装成已执行成功。
- 不修改 `/api/v1/ai/config/bootstrap` 的现有模型、Pro 或 `api_key` 响应契约。
- 不因本工单开启 P4/P5/P6 工具；纯文本闭环应在工具开关关闭时独立可用。

## 四、目标架构

```text
                           /home
                              │
                     Home Conversation Shell
                              │
               ensureActiveThreadForSend()
                              │
                POST /threads/{id}/runs/
                              │
                    Run Readiness Gate
             ┌─────────────┴─────────────┐
             │                           │
       RunService / DB                Celery chat.ai
             │                           │
      Run + Message + Event        Provider Gateway
             │                           │
             └───── StreamWriter / Outbox ───┘
                              │
                       WS + REST Replay
                              │
                     Web Event Reducer
                              │
              Canonical ChatMessage/Block Model
                              │
                   Block Renderer Registry
```

同步历史链路：

```text
iOS ChatMessage/ChatMessageBlock
  → ChatRemoteMessageDTO
  → /api/v1/ai/chat/sync/push/
  → ChatMessage + ChatMessageBlock.payload
  → /api/v1/ai/chat/sync/pull/
  → Web normalizeChatMessage/normalizeChatBlockPayload
  → Canonical Web ViewModel
  → 同 kind 专用渲染器
```

## 五、对话发送恢复方案

### 5.1 阶段 A：确认已配置项在运行进程中生效

本阶段不修改 `CHAT_AI_SERVER_RUNS_ENABLED`。必须先用脱敏诊断信息确认接收请求的 Web 进程、Celery Worker 与部署配置属于同一环境和版本，并核对：

| 检查项 | 成功条件 | 失败结果 |
|---|---|---|
| 配置生效实例 | 所有 Web 实例均加载已完成的配置，实例版本一致 | 部分请求仍返回 50392 |
| 进程重载 | 配置发布时间晚于当前进程启动时间，或进程已按部署流程重载 | 进程继续使用旧配置快照 |
| 请求路由 | BFF/反向代理未命中旧实例、旧容器或错误环境 | 同一用户请求结果不一致 |
| 数据库 | `chat_sync` Run/Event/Context/Tool/Interaction 迁移完整 | 禁止发布 |
| 执行器 | `CHAT_AI_RUN_EXECUTOR=provider` | `disabled` 会导致 queued 不动 |
| 模型绑定 | Chat Scenario 有 active/default 文本模型 | Worker 失败 `no active chat model binding` |
| Provider | 有 active key 与 request URL | Worker 失败 `no active provider credential` |
| Celery | Worker 消费 `chat.ai` | Run 停在 queued |
| Redis/Broker | 生产者与 Worker 可连接 | 任务无法投递 |
| Outbox | `chat.events` Worker/Beat 可用 | WS 不实时，仅能轮询补偿 |
| Channels | WS ticket 与 `/ws/chat/runs/` 可用 | Web 降级 REST replay/polling |
| 出站网络 | Provider HTTPS/DNS/证书正常 | Run failed/interrupted |

### 5.2 阶段 B：纯文本闭环验证

在不改动 Run 开关的前提下，纯文本运行链路基线为：

```text
CHAT_AI_RUN_EXECUTOR=provider
CHAT_AI_AGENTIC_TOOLS_ENABLED=false
CHAT_AI_WAITING_ENABLED=false
CHAT_AI_ASK_USER_ENABLED=false
CHAT_AI_CLIENT_TOOLS_ENABLED=false
```

首先验收不含工具的最小闭环：

```text
create Run
  → queued
  → worker claim + lease
  → running
  → provider text delta
  → block.created / block.delta
  → block.completed
  → usage.final
  → run.completed / run.done
  → assistant message delivery_state=sent
```

P4/P5/P6 工具只能在纯文本闭环稳定后逐项开启。

### 5.3 Run 就绪状态服务

建议新增统一 `ChatRunReadinessService`，避免只检查一个 bool：

```python
@dataclass(frozen=True)
class ChatRunReadiness:
    available: bool
    code: str
    retryable: bool
    checked_at: datetime
    executor: str

class ChatRunReadinessService:
    @classmethod
    def evaluate(cls) -> ChatRunReadiness:
        if settings.CHAT_AI_RUN_EXECUTOR != "provider":
            return unavailable("chat_run_executor_unavailable", retryable=False)
        resolve_chat_route()  # 只返回脱敏结果，不暴露 key
        if not cached_worker_health("chat.ai"):
            return unavailable("chat_run_worker_unavailable", retryable=True)
        return available()
```

说明：

- 请求线程不对 Broker 或 Provider 执行高延迟实时 Ping，而是使用短 TTL 健康快照。
- 就绪结果不返回 API Key、Provider 内网 URL、Celery node 名、数据库堆栈。
- `RunService.create_run()` 仍是最终写入门禁，不信任 Web 传入“可用”状态。

### 5.4 Web 发送状态

Web 需要区分：

| 状态 | Composer | 用户提示 |
|---|---|---|
| 正在检查 | 可输入，暂不发送 | “正在连接对话服务…” |
| 可用 | 可发送 | 常规医疗提示 |
| 服务未开启 | 保留输入 | “对话服务暂未开启” |
| Worker/Broker 暂时不可用 | 保留输入，允许手动重试 | “服务暂时繁忙” |
| Run 已创建 | 显示停止 | queued/running 状态 |
| 失败/中断 | 恢复发送 | 显示原回答重生，不自动重复扣费 |

当前 Web 只在 `createRun()` 返回 true 后清空输入，这一行为应保留；503 失败时不应丢失用户文本。

### 5.5 失败恢复

- 任务投递失败不能让 Run 永久 queued；recovery task 必须重投或终结为可观测失败。
- Worker 取得 lease 后崩溃，超过 TTL 由 recovery 重获或终结。
- Provider 首包超时、流闲置超时、429 和 5xx 按现有错误分类和最大尝试处理。
- 已有可见 delta 后失败，Run 为 `interrupted`，不能无声重头生成。
- WS 不可用时 Web 通过 REST event replay/polling 收敛至相同结果。

## 六、iOS 消息数据模型对齐

### 6.1 Message 字段映射

| iOS `ChatMessage` | 当前 Web/Sync | 目标 |
|---|---|---|
| `id` | Web 无单独本地 ID | Web 以 `server_message_id ?? client_message_id` 建立稳定 view ID |
| `threadId` | `thread_id` | 保持 |
| `role` | user/assistant/system | 改为强类型 union |
| `blocks` | `ChatBlockDTO[]` | 对齐 36 kind 和强类型 payload |
| `clientMessageId` | `client_message_id` | 作为跨端幂等主键 |
| `serverMessageId` | 可选 | 服务端成功后必须存在 |
| `deliveryState` | Web 为任意 string | 限定 pending/sending/sent/failed/read |
| `createdAt` | `created_at` | 保持 ISO8601 |
| `serverUpdatedAt` | `server_updated_at` | 用于增量合并 |
| `isTombstone` | `tombstone` | 不渲染，但必须参与合并和删除 |
| `modelName` | `model_name` | 保持 |
| `usageSummary` | 当前 Sync DTO 未返回 | 新增可选 `usage_summary`，从 Run Usage 安全投影 |

### 6.2 Block 字段映射

| iOS `ChatMessageBlock` | Web 目标类型 | 规则 |
|---|---|---|
| `id` | string UUID | 同一卡片 pending→ready 保持同 ID |
| `anchor` | discriminated union | messageStart/messageEnd/beforeBlock/afterBlock/toolCall |
| `toolCallId` | string/null | 工具行与展示卡关联 |
| `parentToolCallId` | string/null | 嵌套工具调用关系 |
| `parentBlockId` | UUID/null | 块级父子关系 |
| `nodeRole` | timeline/tool/toolPresentation | 不再使用任意 string |
| `payload` | 按 kind 判别的 union | 保留 rawPayload 供前向兼容 |
| `status` | pending/streaming/ready/failed | 非文本 streaming 先显示骨架/状态 |
| `revision` | number | 仅接受更高 revision |
| `orderKey` | number/null | 主排序键 |
| `createdAt/updatedAt` | ISO8601 | 稳定排序与合并后备键 |

### 6.3 36 种 Block 展示矩阵

| kind | Web 目标展示 | 平台动作边界 |
|---|---|---|
| `text` | Markdown/GFM、链接、流式光标 | 完整支持 |
| `deepThought` | 可折叠思考卡、耗时、可见性 | 不展示服务端隐藏推理 |
| `tool` | 工具名、状态、安全摘要 | 不暴露私密参数/结果 |
| `imageGallery` | 响应式图片网格和预览 | 使用受权 URL/下载端点 |
| `fileAttachments` | 文件名、类型、大小、状态 | 仅在有权限时下载 |
| `knowledgeCards` | 知识来源卡、标题、摘要 | 保存动作需服务端 API |
| `translatedText` | 翻译文本区块 | 只读 |
| `mapRoute` | 地点与路线摘要/地图 | 无 Web 地图能力时展示可读列表 |
| `events` | 日期、时间、事件卡 | 写入日历需额外授权 |
| `healthCards` | 健康指标卡 | 默认只读 |
| `pendingMemberToolCards` | 待选成员卡 | Web 可选择时回传 PendingInteraction |
| `toolQuestionCards` | 结构化问题/选项/自由输入 | 防止重复提交 |
| `toolMemberSelectionCards` | 成员选择卡 | 需用户与 Thread 权限 |
| `healthResourceCandidateCards` | 健康资料候选选择 | 支持选择/跳过幂等 |
| `toolConsentCards` | 授权范围、风险、允许/拒绝 | 不默认代表用户同意 |
| `locationPermissionCards` | 定位需求和当前状态 | Web 不能使用时引导到支持的客户端 |
| `structuredHealthCards` | 结构化健康数据列表/预览 | 变更需服务端鉴权 |
| `sleepVisualization` | 睡眠时长、阶段和趋势 | 只读 |
| `stepVisualization` | 步数、目标和趋势 | 只读 |
| `energyVisualization` | 消耗、目标和趋势 | 只读 |
| `nutritionReadVisualization` | 营养摄入读取卡 | Web 只读，不冒充 HealthKit |
| `weatherVisualization` | 天气结果卡 | 只读 |
| `weatherConfigCard` | 城市/定位配置摘要 | 仅在 Web 有实现时可编辑 |
| `searchSummary` | 来源数、摘要、可折叠引用 | 外链使用 noopener |
| `nutritionCards` | 营养项和合计卡 | 写 HealthKit 动作只能客户端执行 |
| `workoutVisualization` | 运动类型、时长、能量、趋势 | 只读 |
| `captureCard` | 相机/相册/文件入口说明 | 仅在 Web 附件上传完成时开放 |
| `html` | 隔离的安全预览 | 严格 sanitize，禁止任意 script |
| `smallTaskCard` | 小任务摘要和跳转 | 目标页不存在时只读 |
| `taskCards` | 任务列表、状态、时间 | 变更状态需鉴权 API |
| `error` | 错误卡和可选重试 | 重试使用原 Run 重生契约 |
| `assistantStatusCard` | 中断/失败/状态卡 | 与 delivery/run 状态一致 |
| `healthResourceReference` | 资料类型、标题、引用、可用性 | 用户无权时不显示敏感内容 |
| `medicalRiskNotice` | 高风险提示 | 不得折叠或弱化主要风险文案 |
| `medicalDisclaimerCard` | 医疗免责提示 | 完成后展示，streaming 时可暂隐藏 |
| `chatGuideCard` | 首条引导、健康指标、推荐问题 | 点击问题直接填入/发送 |

### 6.4 Payload 归一化规则

必须区分两层：

```typescript
interface ChatBlockWireDTO {
  id: string;
  kind: string;
  payload?: unknown;
  // 其他 wire 字段
}

interface CanonicalChatBlock<TKind extends ChatBlockKind = ChatBlockKind> {
  id: string;
  kind: TKind;
  payload: ChatPayloadByKind[TKind];
  rawPayload: unknown;
  status: ChatBlockStatus;
  revision: number;
  orderKey: number | null;
  nodeRole: ChatBlockNodeRole;
  anchor: ChatBlockAnchor | null;
}
```

归一化步骤：

```text
1. 提取 block 元数据，兼容 snake_case/camelCase。
2. 保留 rawPayload，禁止丢弃未知字段。
3. 根据 kind 查找 payload 别名：
   - deepThought / deep_thought
   - taskCards / task_cards
   - imageGallery / image_gallery
4. 如命中 Swift enum 包装 `{case_key:{_0:value}}`，提取 `_0`。
5. 如已是服务端 canonical payload，直接校验。
6. 用 kind-specific parser 生成强类型 payload。
7. 解析失败时生成该 kind 的安全降级卡，不影响整条 Message。
```

文本示例：

```typescript
function unwrapAssociatedValue(raw: unknown, aliases: string[]): unknown {
  const root = asRecord(raw);
  for (const alias of aliases) {
    const wrapped = asRecord(root[alias]);
    if ("_0" in wrapped) return wrapped._0;
  }
  return raw;
}

function normalizeTextPayload(raw: unknown): TextPayload {
  if (typeof asRecord(raw).text === "string") {
    return { text: String(asRecord(raw).text) };
  }
  const value = unwrapAssociatedValue(raw, ["text"]);
  return { text: typeof value === "string" ? value : "" };
}
```

### 6.5 排序、更新与合并

Block 顺序不能使用 `Object.values(blocksById)` 的对象插入顺序。统一规则：

```text
orderKey 有值且不同 → orderKey 升序
orderKey 有值 → 优先于 nil
否则 → createdAt 升序
仍相同 → id 字典序
```

合并规则：

- 同 ID 只接受更高 revision。
- `ready` 不能被更旧 `pending` 覆盖。
- `block.delta` 必须在 revision 严格增加时追加。
- Sync 完整块与 Run Event 实时块使用同一 normalizer。
- 未知 kind 保留 `rawPayload`，展示安全降级卡，不抛出整页错误。
- `toolPresentation` 与工具行按 `toolCallId/parentToolCallId` 联系，不按相邻数组位置猜测。

### 6.6 渲染器注册表

禁止将 36 种类型继续堆在一个 `ChatBlockRenderer.tsx` 的超长 switch 中。目标：

```typescript
const BLOCK_RENDERERS: Partial<{
  [K in ChatBlockKind]: React.ComponentType<BlockRendererProps<K>>
}> = {
  text: TextBlock,
  deepThought: DeepThoughtBlock,
  imageGallery: ImageGalleryBlock,
  fileAttachments: FileAttachmentsBlock,
  // ...
};
```

`ChatBlockRenderer` 只负责：

1. pending/streaming/failed 生命周期外层。
2. 根据 kind 分派。
3. Error Boundary。
4. 未知类型降级。
5. 不在通用层执行医疗、文件、工具或平台动作。

## 七、主页就是对话入口

### 7.1 产品规则

1. 登录成功统一进入 `/home`。
2. `/chat` 只作为兼容重定向，不维护第二套页面。
3. 不显示“新建对话”按钮。
4. 不显示“搜索对话”输入框。
5. 有历史 Thread 时默认打开最近更新且未删除的 Thread。
6. 无历史 Thread 时仍显示可输入 Composer，不禁用发送。
7. 首次发送时系统内部幂等创建 Thread 容器，然后创建 Run。
8. Thread 是技术容器，不是首次发送前的用户任务。

### 7.2 首次发送流程

```text
用户在 /home 输入文本
  → Composer 校验非空与 Run 非 active
  → ThreadContext.ensureActiveThreadForSend()
      ├─ 已有 selectedThreadId：直接返回
      ├─ 有最近 Thread：选中并返回
      └─ 无 Thread：使用单飞锁幂等创建默认 Thread
  → 加载/创建 Thread Preferences
  → RunControl.createRunForThread(threadId, content, context)
  → 成功后清空输入
```

核心代码轮廓：

```typescript
const ensureActiveThreadForSend = async (): Promise<string> => {
  if (selectedThreadId) return selectedThreadId;
  const recent = activeThreads[0];
  if (recent) {
    selectThreadWithoutNavigation(recent.thread_id);
    return recent.thread_id;
  }
  return singleFlight("home-default-thread", async () => {
    const thread = await createInternalThread({ title: "New Chat" });
    selectThreadWithoutNavigation(thread.thread_id);
    return thread.thread_id;
  });
};
```

“不需要新建对话”指用户无需执行新建操作，不代表删除服务端 Thread 实体。Message、Preferences、Run Lock 和 Context 仍需要 Thread ID。

### 7.3 并发与幂等

- 快速连点发送不能创建多个默认 Thread。
- `ensureActiveThreadForSend()` 在同一浏览器使用 Promise single-flight。
- 服务端 Thread push 使用客户端预生成 UUID 幂等 upsert。
- Thread 准备失败时保留输入，允许手动重试。
- Thread 创建成功但 Run 创建失败时复用该 Thread，不重复创建。
- 账号切换/退出时清理本地 selected ID 与 in-flight Promise，不删除服务端 Thread。

### 7.4 侧边栏目标

移除：

```text
sidebar__new
sidebar-search
query / filteredThreads / startNew 相关状态
```

保留：

```text
主页入口
最近对话列表
对话切换
重命名/删除（如产品仍需要）
知识库/医疗/饮食/运动/记忆/设置导航
```

当没有历史时，不显示“请新建”，主区直接展示空态、推荐问题和可用 Composer。

## 八、文件级改动规划

> 本节只是后续实现指引。本次不修改以下任何文件。

### 8.1 服务端 Run 可用性

| 文件 | 改动方向 |
|---|---|
| `chat_sync/ai_services/run_readiness_service.py` | 新建脱敏就绪评估与短 TTL 健康快照 |
| `chat_sync/ai_services/run_service.py` | 创建 Run 前使用统一 readiness 门禁；保留幂等与事务 |
| `chat_sync/ai_runtime/providers/factory.py` | 提供不暴露密钥的 route 配置校验 |
| `chat_sync/ai_api/views.py` | 新增已鉴权 Run readiness 查询，供 Composer 预判 |
| `chat_sync/ai_api/urls.py` | 注册 readiness URL |
| `chat_sync/ai_tasks/run_tasks.py` | 固化 executor 检查、Worker heartbeat 与失败终态语义 |
| `chat_sync/ai_tasks/recovery_tasks.py` | 处理超时 queued/租约丢失 Run，避免永久排队 |
| `chat_sync/tests/ai_services/test_run_readiness.py` | 新建 executor/model/provider/worker 矩阵测试，不修改 Run 开关实现 |
| `chat_sync/tests/ai_services/test_run_api.py` | 使用既有 50392 契约作为回归基线，增加运行实例诊断关联与脱敏响应测试 |
| `chat_sync/tests/ai_services/test_p2_streaming.py` | 完整验证 provider 文本闭环和终态事件顺序 |
| 生产部署与进程清单 | 不改 Run 开关；核对 Web 实例配置版本，并启动/验证 `chat.ai/chat.events/chat.recovery` 消费者 |

### 8.2 服务端消息契约

| 文件 | 改动方向 |
|---|---|
| `chat_sync/serializers.py` | 增加可选 `usage_summary`，保持 iOS 现有字段兼容 |
| `chat_sync/views.py` | 安全投影 usage；保留 Block raw payload，不破坏 Swift Codable wire 形状 |
| `chat_sync/tests/test_sync.py` | 增加 36 kind round-trip、Swift `_0` payload、revision/order/anchor/parent 关系测试 |
| `chat_sync/tests/contracts/schemas/block.v1.schema.json` | 从“任意 payload object”扩展为基础 envelope + kind 专项 schema |
| `chat_sync/tests/contracts/valid/blocks/` | 每种 iOS kind 至少一个真实有效 fixture |
| `chat_sync/tests/contracts/invalid/blocks/` | 增加错误状态、revision、关联值、敏感字段 fixture |

`ChatMessageBlock` 现有表已包含 kind/status/revision/order/tool/parent/node/anchor/payload，本工单原则上不需修改表结构。`usage_summary` 可从现有 `ChatUsageRecord` 投影，不应重复建表。

### 8.3 Web 消息模型与渲染

| 文件 | 改动方向 |
|---|---|
| `chat-web/types/chat.ts` | 定义 36 kind union、node role、anchor、payload map、usage summary 和 canonical block |
| `chat-web/types/sync.ts` | 区分 Wire DTO 与 Canonical Message，收紧 delivery state |
| `chat-web/lib/api/chat-sync-api.ts` | 不再只做元数据拆分，调用统一归一化器 |
| `chat-web/lib/chat/block-normalizer.ts` | 新建 snake/camel、Swift `_0`、canonical payload 归一化 |
| `chat-web/lib/chat/message-normalizer.ts` | 新建 Message 字段、tombstone、delivery、usage 归一化 |
| `chat-web/lib/chat/block-order.ts` | 新建 orderKey/createdAt/id 稳定排序 |
| `chat-web/lib/event-reducer.ts` | Sync 和 Event 共用 normalizer，修正 rich block update 与排序 |
| `chat-web/components/chat/home/ChatBlockRenderer.tsx` | 改为生命周期外层 + registry 分派 + Error Boundary |
| `chat-web/components/chat/blocks/` | 新增按职责分组的文本、媒体、健康、任务、工具、风险渲染器 |
| `chat-web/components/chat/home/ChatMessages.tsx` | 按 Message 渲染各自 blocks，不全局复用同一 blocks 集合；展示 delivery/error/usage |
| `chat-web/app/globals.css` | 增加卡片设计 token、宽度、加载、失败、移动端断点和打印样式 |
| `chat-web/tests/block-normalizer.test.ts` | 新增 36 kind、Swift payload、未知字段与失败降级测试 |
| `chat-web/tests/block-renderer.test.tsx` | 新增每个 kind 的非崩溃与核心字段展示测试 |
| `chat-web/tests/event-reducer.test.ts` | 增加 rich block create/update/completed、乱序、断线回放测试 |
| `chat-web/contracts/spark-chat-v1/` | 通过同步脚本对齐服务端 schema/fixtures，禁止手工漂移 |

### 8.4 Web 主页与 Thread 编排

| 文件 | 改动方向 |
|---|---|
| `chat-web/components/sidebar/WorkspaceSidebar.tsx` | 移除新建按钮、搜索框和相关状态，保留最近 Thread |
| `chat-web/context/ThreadContext.tsx` | 新增 `ensureActiveThreadForSend()` single-flight；默认选中最近 Thread |
| `chat-web/context/RunControlContext.tsx` | `createRun` 使用明确 threadId，不依赖旧 render closure 的 null ID |
| `chat-web/context/ChatContextProvider.tsx` | 支持首次自动 Thread 建立后加载 Preferences，再创建 Turn Context |
| `chat-web/components/chat/home/ChatComposer.tsx` | 去掉“请先新建”阻断；发送内部先 ensure Thread |
| `chat-web/app/(workspace)/home/[[...threadId]]/page.tsx` | 保持 `/home` 为对话主页，可选 Thread 深链接只做历史定位 |
| `chat-web/app/(workspace)/chat/[[...threadId]]/page.tsx` | 继续只重定向 `/home` |
| `chat-web/tests/home-conversation-entry.test.tsx` | 新增无 Thread 直接发送、单飞创建、失败保留输入测试 |
| `chat-web/tests/components.test.tsx` | 断言不再出现新建/搜索对话入口 |

### 8.5 iOS 只读参考，禁止改动

```text
LookHealthClient/SparkClient/SparkClient/Projects/Features/Chat/Domain/ChatMessage/ChatMessage.swift
LookHealthClient/SparkClient/SparkClient/Projects/Core/Networking/API/AI/ChatRemoteAPI.swift
LookHealthClient/SparkClient/SparkClient/Projects/Features/Chat/Presentation/ChatView/Components/ChatMessageBlock+Render.swift
LookHealthClient/SparkClient/SparkClient/Projects/Features/Chat/Domain/ChatMessage/BlockPayloads/
```

这些文件只是 Web 对齐的事实源，本工单不授权修改它们。

## 九、核心业务逻辑与代码轮廓

### 9.1 Run 创建

```python
def create_run(user, thread_id, payload, idempotency_key):
    readiness = ChatRunReadinessService.require_available()
    validate_idempotency_key(idempotency_key)

    with transaction.atomic():
        existing = lock_idempotent_run(user.id, idempotency_key)
        if existing:
            assert_same_request_hash(existing, payload)
            return existing, True

        thread, run_lock = lock_owned_thread(user.id, thread_id)
        assert_no_active_run(run_lock)
        preferences = freeze_preferences(thread, payload)
        user_message = create_user_message_and_text_block(payload)
        assistant_message = create_pending_assistant_message()
        run = create_queued_run(...)
        append_outbox_event(run, "run.queued")
        transaction.on_commit(lambda: enqueue_provider_run(run.id))
        return run, False
```

### 9.2 主页发送

```typescript
async function sendFromHome(text: string): Promise<boolean> {
  const content = text.trim();
  if (!content || activeRun) return false;

  const threadId = await threads.ensureActiveThreadForSend();
  const turnContext = await context.getOrLoadTurnContext(threadId);
  const accepted = await runs.createRunForThread(threadId, content, turnContext);

  if (accepted) {
    clearComposer();
    context.clearDraft();
  }
  return accepted;
}
```

### 9.3 消息归一化

```typescript
function normalizeChatBlock(raw: ChatBlockWireDTO): CanonicalChatBlock {
  const kind = normalizeBlockKind(raw.kind);
  const rawPayload = raw.payload ?? stripEnvelopeFields(raw);
  const parser = BLOCK_PAYLOAD_PARSERS[kind];

  return {
    id: requireUUID(raw.id),
    kind,
    payload: parser ? parser(rawPayload) : makeUnknownPayload(rawPayload),
    rawPayload,
    status: normalizeBlockStatus(raw.status),
    revision: nonNegativeInteger(raw.revision),
    orderKey: finiteNumberOrNull(raw.order_key ?? raw.orderKey),
    nodeRole: normalizeNodeRole(raw.node_role ?? raw.nodeRole),
    anchor: normalizeAnchor(raw.anchor),
    toolCallId: stringOrNull(raw.tool_call_id ?? raw.toolCallId),
    parentToolCallId: stringOrNull(raw.parent_tool_call_id ?? raw.parentToolCallId),
    parentBlockId: uuidOrNull(raw.parent_block_id ?? raw.parentBlockId),
    createdAt: isoDateOrNull(raw.created_at ?? raw.createdAt),
    updatedAt: isoDateOrNull(raw.updated_at ?? raw.updatedAt),
  };
}
```

### 9.4 渲染安全边界

```typescript
function ChatBlockRenderer({ block }: { block: CanonicalChatBlock }) {
  if (needsPendingPresentation(block)) return <PendingBlock kind={block.kind} />;
  const Renderer = BLOCK_RENDERERS[block.kind];
  if (!Renderer) return <UnsupportedBlock kind={block.kind} raw={block.rawPayload} />;
  return <BlockErrorBoundary blockId={block.id}><Renderer block={block as never} /></BlockErrorBoundary>;
}
```

Unknown/failure 卡只显示类型名和安全 fallback text，不将 raw JSON 直接输出到 DOM。

## 十、错误模型

| 错误 | HTTP/业务码 | retryable | Web 处理 |
|---|---:|---:|---|
| 运行实例判定 Run 门禁关闭 | 503/50392 | false | 保留输入；记录实例与配置版本，提示服务不可用 |
| executor 不可用 | 503/新码 | false | 保留输入，禁止无意义重试 |
| Worker/Broker 暂时不可用 | 503/新码 | true | 手动重试，指数退避刷新 readiness |
| 模型绑定缺失 | 503/新码 | false | 管理员修复配置 |
| Provider 鉴权失败 | Run failed | false | 展示生成失败，不暴露 key |
| Provider 429/5xx/超时 | Run failed/interrupted | 按映射 | 显示可重生状态 |
| Thread 准备失败 | 4xx/5xx | 按错误 | 保留输入，不重复新建 |
| Block payload 不兼容 | 不中断 Message | false | 单 Block 安全降级 |
| 平台能力不存在 | 非服务错误 | false | 只读/说明卡，不伪造成功 |

## 十一、测试方案

### 11.1 Run 链路测试

1. 已配置环境中所有目标 Web 实例读取到一致的脱敏配置版本，不再返回 50392。
2. executor 不可用时在创建前返回明确不就绪，不创建永久 queued Run。
3. 无 Chat model binding 时不就绪。
4. 无 Provider credential 时不就绪。
5. 完整运行链路下 Create Run 返回 202。
6. Worker 从 queued 进入 running，最终 completed。
7. 文本 delta 按 revision 单调追加。
8. WS 丢包后 REST replay 得到相同 Block。
9. 同幂等键相同 payload 返回原 Run，不重复生成。
10. 取消、失败、中断均收敛至唯一终态。

### 11.2 iOS Message 合同测试

1. 从 iOS 真实 JSON fixture 抽取 36 种 kind。
2. 每种 fixture 经 `sync push → DB → sync pull` 后关键 payload 不丢失。
3. snake_case/camelCase 元数据都可识别。
4. Swift `{case:{_0:value}}` 与服务端 canonical payload 归一到同一 ViewModel。
5. anchor 五种变体完整 round-trip。
6. tool/parent/block 父子关系不丢失。
7. revision 旧包不覆盖新包。
8. `ready` 不退回 `pending`。
9. tombstone Message 不展示但会正确从界面移除。
10. usage summary 缺失时向后兼容。

### 11.3 Web 渲染测试

- 36 种 kind 每种至少一个组件测试。
- 每种展示至少一个关键用户字段，不能只断言“未崩溃”。
- pending/streaming/ready/failed 四状态覆盖。
- HTML 注入、恶意 URL、超长文本、损坏图片与缺字段 fixture 覆盖。
- 平台专属卡不显示假的“已授权/已写入”。
- 单个坏 Block 不影响同 Message 其他 Block。
- 宽屏、小屏、键盘导航、屏幕阅读器与 reduced motion 验收。

### 11.4 主页入口测试

1. `/` 登录后进入 `/home`。
2. `/home` 直接展示对话和 Composer。
3. 页面不存在“新建对话”按钮。
4. 页面不存在“搜索对话”输入框。
5. 有 Thread 时自动选中最近一条。
6. 无 Thread 时 Composer 仍可输入并发送。
7. 首次发送只准备一条 Thread。
8. Thread 或 Run 失败时保留输入文本。
9. 快速连点发送不产生多个 Thread/Run。
10. 账号切换后不显示上一账号 Thread。

## 十二、可观测性

### 12.1 日志

```text
chat_run.readiness.checked
chat_run.create.rejected_not_ready
chat_run.create.accepted
chat_run.enqueue.succeeded / failed
chat_run.worker.claimed
chat_run.provider.first_event
chat_run.completed / failed / interrupted
chat_web.block.normalize_failed
chat_web.block.unsupported_kind
chat_web.home.thread.ensure_started / reused / created / failed
```

不得记录 Provider key、用户原始问题、健康卡原始数据、附件受权 URL 或工具私密结果。

### 12.2 指标

```text
chat_run_create_total{outcome,error_code}
chat_run_queue_latency_seconds
chat_run_time_to_first_event_seconds
chat_run_duration_seconds{terminal_status}
chat_run_stuck_queued_total
chat_run_worker_heartbeat_age_seconds
chat_block_normalize_total{kind,outcome}
chat_block_render_fallback_total{kind,reason}
chat_home_thread_ensure_total{outcome}
```

发布后任意 `chat_run_stuck_queued_total > 0` 或已知 iOS kind 进入 unsupported fallback，均需触发告警。

## 十三、发布顺序与回滚

### 13.1 实施顺序

1. 固化 iOS 36 kind 合同 fixture，不先改服务端 wire 形状。
2. 实现 Web normalizer、强类型模型和基础渲染器。
3. 实现平台专属卡的只读/移交状态。
4. 实现主页 `ensureActiveThreadForSend()` 和移除新建/搜索入口。
5. 实现 Run readiness 与运行实例诊断，不修改既有 Run 开关配置。
6. 在测试环境启动 provider executor 和 Celery 队列。
7. 在既有 Run 开关配置下完成纯文本 E2E。
8. 灰度 Web 用户，监控 queued、TTFT、失败率和 block fallback。

### 13.2 回滚

- Run 回滚：本工单不以修改 `CHAT_AI_SERVER_RUNS_ENABLED` 作为回滚手段；按现有发布平台回滚应用版本，并保留历史只读和用户输入。
- Renderer 回滚：按 kind feature flag 回退至安全只读卡，不改动服务端原始 payload。
- 主页回滚：保留自动选中最近 Thread，禁止回退到强制用户点击“新建对话”。
- 任何回滚不删除 Thread、Message、Block、Run 或 Event 数据。

## 十四、子工单

### CHAT-WEB-021A：Run 生产就绪与纯文本闭环

- readiness 服务、运行实例诊断和健康指标；不修改 Run 开关。
- Provider/Celery/Outbox/Recovery 全链路验收。
- 解决 50392，不产生永久 queued Run。

### CHAT-WEB-021B：iOS Message/Block 合同基线

- 36 kind fixture、schema、round-trip 和 usage summary。
- 冻结 snake/camel/Swift `_0` 规则。

### CHAT-WEB-021C：Web 归一化与渲染器

- canonical types、normalizer、order/merge、registry、36 kind 渲染。
- 安全降级、HTML 清洗和无障碍。

### CHAT-WEB-021D：主页直达对话

- 移除新建/搜索入口。
- 默认最近 Thread。
- 首次发送内部幂等准备 Thread。

### CHAT-WEB-021E：综合 E2E 与发布门禁

- 空账号首次发送、历史共用、流式、断线、卡片和回滚验收。

## 十五、完成定义

- [ ] `/home` 直接是可输入、可发送的对话页。
- [ ] Web 不再显示“新建对话”。
- [ ] Web 不再显示“搜索对话”。
- [ ] 无 Thread 时首次发送只准备一条内部 Thread。
- [ ] Thread/Run 失败不清空用户输入。
- [ ] 生产 Run readiness 为 available。
- [ ] Create Run 不再返回 50392。
- [ ] Run 能从 queued 进入 running 并收敛到终态。
- [ ] 纯文本 Provider 回答能实时展示并在刷新后保留。
- [ ] 不存在永久 queued Run。
- [ ] Web Message 字段对齐 iOS 语义。
- [ ] 36 种 iOS Block kind 均有明确 Web 渲染或平台限制卡。
- [ ] 已知 iOS kind 不再进入通用“需要更新版本”降级。
- [ ] Swift `_0` 关联值 payload 能正确归一化。
- [ ] Block revision、order、anchor 和工具父子关系不丢失。
- [ ] 单卡解析/渲染失败不影响整条消息。
- [ ] HTML、链接、附件和健康数据通过安全验收。
- [ ] 没有修改任何 iOS、Android 或 HarmonyOS 代码。
- [ ] 没有修改 AI config bootstrap、Pro 或 `api_key` 对外契约。

## 十六、发布门禁

任一条出现即禁止发布：

1. 任一目标 Web 实例仍返回 50392，或实例间读取到的配置版本不一致。
2. `chat.ai` Worker 未消费生产队列。
3. Chat model binding 或 Provider credential 缺失。
4. Create Run 成功但在验收时间窗内一直 queued。
5. Web 仍要求先点击“新建对话”。
6. Web 仍展示“搜索对话”入口。
7. 无 Thread 账号的 Composer 被禁用。
8. 同一首次发送创建多个 Thread 或多个 Run。
9. 任一已知 iOS Block kind 仍显示通用未知卡。
10. iOS 真实卡片 JSON 经 Sync 后丢失 payload、revision、order 或父子关系。
11. Web 将 HealthKit/定位/授权等平台动作伪装为成功。
12. 需要修改 iOS 才能展示现有同步消息。

## 十七、最终结论

Web 当前无法发送对话的直接表现是处理请求的服务端进程返回 50392。由于 `CHAT_AI_SERVER_RUNS_ENABLED` 已配置完成，本工单不再给出该开关的配置方案；需要查明目标进程为何仍读取为关闭态，并继续验证 Provider executor、模型路由、Celery Worker、Broker、Outbox 和 Recovery 是否达到就绪状态。

Web 卡片问题的根因不是服务端没有保存 kind，而是 Web 没有把 iOS Swift Codable payload 归一化为强类型视图模型，也没有对应的 36 kind 渲染器。后续应保持 iOS 和服务端 wire 兼容，在 Web Adapter 层解耦差异。

主页优化不删除 Thread 技术实体，而是删除用户在对话前的管理负担：`/home` 直接可发送，首次发送时由系统幂等准备 Thread，不再显示新建和搜索入口。
