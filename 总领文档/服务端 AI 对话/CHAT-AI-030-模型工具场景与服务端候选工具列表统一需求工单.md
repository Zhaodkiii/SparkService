# CHAT-AI-030 模型工具场景与服务端候选工具列表统一需求工单

> 创建日期：2026-08-27  
> 状态：待方案确认，未开始实现  
> 优先级：P0  
> 关联工单：CHAT-AI-029、CHAT-AI-024  
> 范围：SparkService 服务端 AI 对话与 Web 工具可见性  
> 约束：本工单只整理需求、契约和落地方案，不修改业务代码、数据库、配置或任何客户端代码。

## 一、问题定义

当前 AI 场景配置中存在模型、场景和 `aiToolScenarios` 等配置，但无法清晰回答：

1. 当前对话使用的是哪个模型。
2. 该模型场景理论上绑定了哪些工具场景。
3. 哪些工具是真正由 SparkService 服务端注册并可以执行的工具。
4. 哪些工具因为平台、权限、上下文或功能开关被过滤。
5. 本次 Run 最终会把哪些 Tool Schema 发送给模型。

如果直接把 `aiToolScenarios` 返回给 Web 或直接发送给模型，会产生以下风险：

- 配置中存在工具，但服务端没有对应执行器。
- 配置工具属于客户端能力，Web 无法执行。
- 模型支持工具调用，但当前 Provider 不支持某个工具特性。
- 工具需要知识库、成员、附件或授权，但当前上下文不满足。
- 前端显示的工具列表与 Provider 实际收到的工具列表不一致。
- Thread 配置变更后，正在运行的 Run 工具边界发生漂移。

## 二、已确认的产品决策

### 2.1 工具列表不是模型直接决定

对齐 DeepTutor：

> 工具列表由服务端运行时先计算出候选工具列表；模型只能从服务端传给它的 Tool Schema 中选择是否调用某个工具。

模型只能决定：

- 本轮是否调用工具。
- 调用哪个已经提供的工具。
- 为工具生成什么参数。

模型不能决定：

- 把未注册工具加入本轮。
- 绕过 `aiToolScenarios` 直接调用任意工具。
- 把客户端工具变成服务端工具。
- 修改服务端工具清单、权限、风险和执行模式。

### 2.2 `aiToolScenarios` 的定位

`aiToolScenarios` 不再作为“最终对话工具列表”，而是模型场景的工具绑定声明：

```text
AI 对话 capability/scenario
        ↓
解析到实际模型
        ↓
读取该模型绑定的 aiToolScenarios
        ↓
与服务端 Tool Registry 求交集
        ↓
按平台、权限、上下文、Provider 能力过滤
        ↓
生成本次 Run 的 Effective Tool Manifest
        ↓
转换为 Provider Tool Schema
```

因此，`aiToolScenarios` 是“允许候选来源”，不是“执行授权”，也不是“直接展示结果”。

### 2.3 只向对话提供服务端通用工具

第一阶段只从 SparkService 独立维护的服务端工具枚举和服务端 Registry 中取值，加入 Web 对话候选列表。

服务端工具必须同时满足：

- 已在 SparkService Tool Registry 注册。
- 有有效的 Tool Definition 和 JSON Schema。
- 有服务端 Adapter/Executor。
- 工具名称存在于服务端工具枚举。
- 通过 ToolPolicy、权限和上下文校验。
- 当前模型/Provider 支持 Tool Calling。

客户端 `SparkToolName` 中的工具不会进入服务端工具枚举，也不会进入 Web Provider 的可执行工具列表；如未来需要跨端协作，另走客户端工具协议，见 CHAT-AI-029。

### 2.4 模型绑定中的服务端工具配置

现有 `AIScenarioModelBinding.ai_tool_scenarios` 同时承载场景工具声明，无法在后台清晰区分“服务端对话工具”和“客户端能力工具”。本工单新增独立的服务端工具配置字段，由后台管理系统在“编辑模型/编辑场景模型绑定”页面勾选维护。

建议字段：

```python
server_tool_scenarios = models.JSONField(
    default=list,
    blank=True,
    db_comment="场景模型绑定的 SparkService 服务端工具场景编码列表",
)
```

字段语义：

- `server_tool_scenarios` 是模型场景可使用的服务端工具场景白名单。
- 只保存工具场景编码和可选版本，不保存执行器实例、Provider Schema 或权限结果。
- 后台保存时必须通过服务端工具枚举和 Tool Registry 校验工具是否存在、是否有有效 Executor。
- `ai_tool_scenarios` 不再用于直接推断 Web/服务端可执行工具；历史数据需要迁移或标记来源后再参与解析。
- 客户端工具不写入 `server_tool_scenarios`，也不在该字段中以“工具类型”区分。
- 不新增 `tool_type`、`client_tools` 或同义字段；服务端工具和客户端工具通过各自的名称枚举、注册表和协议完全隔离。

推荐长期语义：

```text
模型/场景绑定
├── server_tool_scenarios   # 后台可勾选；服务端对话候选工具
└── ai_tool_scenarios       # 兼容旧配置/其他场景声明，不能直接下发

Tool Registry
└── SparkService server tools  # 仅登记服务端可执行工具

Client Tool Registry
└── SparkToolName              # 仅由客户端维护，不进入服务端工具配置
```

在完成兼容迁移后，服务端对话解析器只以 `server_tool_scenarios` 作为服务端工具来源；客户端工具由客户端 `SparkToolName`、客户端能力清单和 CHAT-AI-029 协议管理，不从模型绑定的服务端字段读取。

### 2.4.1 服务端工具独立枚举

服务端新增独立的工具名称枚举，不复用客户端 `SparkToolName`。枚举只收录当前 SparkService 已有或明确计划由服务端 Executor 承载的工具：

```python
class SparkServerToolName(models.TextChoices):
    ASK_USER = "ask_user", "询问用户"
    SEARCH_KNOWLEDGE_BAG = "search_knowledge_bag", "搜索知识库"
    GET_CURRENT_MEMBER = "get_current_member", "获取当前成员"
    QUERY_MEMBER_PROFILE = "query_member_profile", "查询成员资料"
    LIST_MEMBER_HEALTH_SOURCES = "list_member_health_sources", "检索成员健康资料"
    GET_HEALTH_RESOURCE_CONTEXT = "get_health_resource_context", "获取健康资料解读上下文"
    READ_SOURCE = "read_source", "读取资料"
```

说明：

- 以上名称必须与 `chat_sync/ai_runtime/tools/registry.py` 中的服务端 Executor 一一对应。
- 新增服务端工具时，先新增服务端枚举、Registry、Schema、Policy 和测试，再允许后台勾选。
- 客户端 `SparkToolName`（健康、定位、日历、客户端 UI 等）保持独立，不复制到此枚举。
- “能否用于当前对话”由服务端枚举 + Registry + Policy + 上下文运行时计算，不依赖 `target` 字段。
- 枚举是配置白名单，不代表当前 Run 一定可用；最终仍需经过模型能力、权限、上下文和功能开关检查。

### 2.5 后台管理系统交互

编辑 `AIScenarioModelBinding` 时新增独立区域：

```text
服务端工具场景
☑ 读取资料 read_source
☑ 联网搜索 web_search
☑ 用户问答 ask_user
☐ 写入记忆 write_memory
☐ 执行代码 exec
```

后台列表只展示 `SparkServerToolName` 枚举和服务端 Registry 的交集，并显示：

- 工具显示名称和编码。
- 工具版本。
- 风险等级和副作用。
- 是否有服务端 Executor。
- 所需权限和上下文。
- 当前是否启用。

后台不得展示或勾选客户端 `SparkToolName`；如果历史数据中存在客户端工具编码，保存时必须提示并拒绝，不能静默写入服务端字段。

保存校验顺序：

```text
后台提交 server_tool_scenarios
        ↓
校验名称/版本格式
        ↓
查询 Tool Registry
        ↓
校验名称属于 SparkServerToolName
        ↓
校验 Executor、Schema、Policy 有效
        ↓
去重并稳定排序
        ↓
保存模型绑定
        ↓
记录配置版本和审计日志
```

### 2.6 服务端对话解析优先级

服务端 Run 创建时，工具来源必须明确为：

```text
当前场景
  → 解析 AIScenarioModelBinding
  → 读取 server_tool_scenarios
  → 查询 Tool Registry
  → SparkServerToolName 服务端枚举过滤
  → Provider/权限/上下文/用户偏好过滤
  → Effective Tool Manifest
```

不得使用以下来源直接生成 Provider Tool Schema：

- Web 请求中上报的工具名称。
- 客户端 `client_tools` 列表。
- 未经过 Registry 校验的 `ai_tool_scenarios` 原始 JSON。
- 前端本地工具配置。

`server_tool_scenarios` 只定义“场景允许尝试哪些服务端工具”；用户权限、上下文、模型能力和功能开关仍然由运行时二次过滤。

### 2.7 与客户端工具的完全区分

服务端和客户端工具通过独立名称枚举、独立注册表和独立执行协议完全隔离：

```json
{
  "name": "get_current_location",
  "supported_platforms": ["ios", "android", "harmonyos"],
  "required_permissions": ["location"],
  "has_executor": false
}
```

该工具：

- 不得被后台加入 `server_tool_scenarios`。
- 不得进入 Web Provider Tool Schema。
- Web 只能展示“需要移动端授权/当前不可用”。
- 移动端未来通过 client capability 注册和 PendingInteraction 执行。

客户端工具不参与服务端工具列表计算；服务端工具列表只认 `SparkServerToolName` 和服务端 Registry，不通过 `target` 做过滤。

## 三、DeepTutor 对齐实现

DeepTutor 的实际职责划分如下：

```text
ToolRegistry
  = 注册全部工具、获取定义、生成 Schema

compose_enabled_tools
  = 根据用户开关、上下文、Capability 组合本轮工具名

build_openai_schemas
  = 将本轮工具名转换为 OpenAI function schemas

AgentLoop
  = 将 schemas 发送给模型，模型使用 tool_choice=auto 选择调用

Dispatcher/Policy
  = 服务端再次校验并执行模型返回的 Tool Call
```

SparkService 需要保留这个职责边界，但将进程内列表升级为可审计的 Run 快照：

```text
aiToolScenarios
        ↓
Scenario/Model Resolver
        ↓
Server Tool Registry
        ↓
Tool Composition
        ↓
Tool Policy Filter
        ↓
Effective Tool Manifest
        ↓
Provider Tool Schema
        ↓
Model Tool Call
```

## 四、统一工具解析算法

### 4.1 输入

服务端运行时必须收集以下输入：

```json
{
  "capability": "chat",
  "capability_version": "v1",
  "scenario_key": "chat.default",
  "resolved_model": "doubao-pro",
  "model_supports_tool_use": true,
  "ai_tool_scenarios": [
    "read_source",
    "web_search",
    "ask_user",
    "get_current_location"
  ],
  "thread_enabled_tools": [
    "web_search"
  ],
  "platform": "web",
  "permissions": [],
  "context": {
    "has_sources": true,
    "has_member": true,
    "has_knowledge_base": false
  }
}
```

### 4.2 过滤顺序

过滤顺序必须固定，避免不同入口得到不同结果：

```text
1. 解析 capability/scenario 到最终模型
2. 读取最终模型绑定的 aiToolScenarios
3. 校验工具名称和版本
4. 与 SparkService Tool Registry 求交集
5. 与 `SparkServerToolName` 服务端枚举求交集
6. 过滤没有服务端执行器的工具
7. 过滤模型/Provider 不支持 Tool Calling 的情况
8. 过滤 Thread 用户关闭的普通工具
9. 过滤权限不满足的工具
10. 过滤 required_context 不满足的工具
11. 应用 feature flag、风险和场景 Policy
12. 稳定排序、去重并生成 manifest_hash
13. 冻结到 Run/ContextSnapshot
14. 由 Manifest 生成 Provider Tool Schema
```

### 4.3 伪代码

```python
def build_effective_tool_manifest(run_context):
    route = resolve_model_route(
        capability=run_context.capability,
        scenario_key=run_context.scenario_key,
    )

    configured_names = route.ai_tool_scenarios
    server_names = set(SparkServerToolName.values)
    allowed_names = [name for name in configured_names if name in server_names]
    registry_entries = server_registry.get_entries(allowed_names)

    candidates = []
    for entry in registry_entries:
        if not entry.has_executor:
            continue
        if not route.supports_tool_use:
            continue
        if not policy_allows(entry, run_context):
            continue
        if not context_satisfies(entry.policy.required_context, run_context):
            continue
        if is_user_disabled(entry.name, run_context.preferences):
            continue
        candidates.append(entry.freeze())

    return freeze_manifest(stable_unique_sort(candidates))
```

## 五、工具配置模型

### 5.1 模型场景绑定

模型配置只声明工具场景，不直接声明执行器对象：

```json
{
  "scenario_key": "chat.default",
  "model_key": "doubao-pro",
  "aiToolScenarios": [
    {
      "name": "read_source",
      "version": "v1",
      "required": true
    },
    {
      "name": "web_search",
      "version": "v1",
      "required": false
    },
    {
      "name": "ask_user",
      "version": "v1",
      "required": true
    }
  ]
}
```

在 SparkService 的模型绑定记录中，对应结构补充为：

```python
class AIScenarioModelBinding(models.Model):
    scenario = models.CharField(...)
    model = models.ForeignKey(...)
    ai_tool_scenarios = models.JSONField(default=list, blank=True)
    server_tool_scenarios = models.JSONField(default=list, blank=True)
```

其中 `server_tool_scenarios` 是本工单新增字段；最终字段名、JSON 元素格式和历史数据迁移策略需在 P0 契约评审中冻结。

### 5.2 服务端 Tool Registry

Registry 负责声明真实执行能力：

```json
{
  "name": "web_search",
  "version": "v1",
  "execution_mode": "immediate",
  "has_executor": true,
  "supported_platforms": ["web", "ios", "android", "harmonyos"],
  "required_permissions": [],
  "required_context": [],
  "risk": "low",
  "side_effect": "none",
  "timeout_ms": 15000,
  "schema_hash": "sha256:...",
  "policy_version": "v1"
}
```

### 5.3 最终 Run Manifest

Run 中保存经过计算的最终清单：

```json
{
  "run_id": "run_123",
  "scenario_key": "chat.default",
  "resolved_model": "doubao-pro",
  "source_server_tool_scenarios": ["read_source", "web_search", "ask_user"],
  "effective_tools": [
    {
      "name": "read_source",
      "status": "enabled",
      "reason": "scenario_enabled_and_server_executor_available"
    },
    {
      "name": "web_search",
      "status": "enabled",
      "reason": "scenario_enabled_and_server_executor_available"
    },
    {
      "name": "ask_user",
      "status": "enabled",
      "execution_mode": "pause",
      "reason": "required_interaction_tool"
    }
  ],
  "filtered_tools": [],
  "manifest_hash": "sha256:...",
  "generated_at": "2026-08-27T10:00:00Z"
}
```

## 六、用户可见接口设计

### 6.1 场景工具预览

用于回答“该模型场景理论上配置了哪些工具”：

```http
GET /api/v1/ai/config/scenarios/{scenario_key}/tools/
```

返回：

- 场景和模型信息。
- `aiToolScenarios` 原始绑定声明。
- 工具是否在服务端 Registry 注册。
- 工具版本和显示名称。
- 是否需要客户端能力。

该接口不能代表本次 Run 的最终工具权限。

### 6.2 Thread 有效工具目录

用于回答“当前对话可以配置哪些工具”：

```http
GET /api/v1/ai/chat/threads/{thread_id}/tools/
```

保留现有接口语义，但数据来源必须改为统一解析器，不能独立维护一套工具判断逻辑。

### 6.3 Run 有效工具快照

用于回答“这一轮实际给模型提供了哪些工具”：

```http
GET /api/v1/ai/chat/threads/{thread_id}/runs/{run_id}/tools/
```

必须返回：

- `scenario_key`
- `resolved_model`
- `source_ai_tool_scenarios`
- `effective_tools`
- `filtered_tools`
- `manifest_hash`
- `generated_at`

Provider 请求日志和 Tool Call 记录必须能够通过 `manifest_hash` 对应到这份快照。

## 七、过滤结果与用户解释

每个未进入最终列表的工具必须保留安全原因码：

| 原因码 | 说明 |
|---|---|
| `not_registered` | 场景配置了工具，但服务端 Registry 没有注册 |
| `executor_missing` | 有定义但没有服务端执行器 |
| `client_only` | 工具只能由客户端执行 |
| `model_unsupported` | 当前模型/Provider 不支持工具调用 |
| `user_disabled` | 用户在 Thread 设置中关闭 |
| `permission_denied` | 用户或场景权限不足 |
| `context_missing` | 缺少资料、成员、知识库等上下文 |
| `feature_disabled` | 服务端功能开关关闭 |
| `policy_denied` | ToolPolicy 拒绝 |
| `invalid_schema` | 工具 Schema 无效或版本不兼容 |

Web 文案示例：

```text
web_search：已启用，服务端执行
read_source：当前不可用，需要先添加资料
get_current_location：当前 Web 不可用，需要移动端授权
unknown_tool：该工具未在服务端注册
```

## 八、关键落地模块

### 8.1 服务端

```text
chat_sync/ai_runtime/tools/registry.py
chat_sync/ai_runtime/tools/scoped_registry.py
chat_sync/ai_runtime/tools/composition.py
chat_sync/ai_runtime/tools/policy.py
chat_sync/ai_runtime/providers/factory.py
chat_sync/ai_services/tool_catalog_service.py
chat_sync/ai_services/context_builder.py
chat_sync/ai_models/context.py
chat_sync/ai_models/tool.py
chat_sync/ai_tasks/run_tasks.py
```

建议新增统一职责模块：

```text
chat_sync/ai_services/effective_tool_manifest_service.py
```

该模块负责：

- 解析 scenario/model 绑定。
- 读取 `server_tool_scenarios`。
- 查询服务端 Registry。
- 应用平台、权限、上下文和模型能力过滤。
- 生成稳定排序的 Manifest。
- 计算 `manifest_hash`。
- 将 Manifest 写入 Run/ContextSnapshot。

### 8.2 Web

Web 只消费服务端返回的安全投影：

```text
chat-web/lib/tools/
chat-web/components/chat/
chat-web/types/chat.ts
chat-web/contracts/spark-chat-v1/
```

Web 不自行读取 `aiToolScenarios`，不自行判断工具是否可执行，也不自行拼接 Provider Tool Schema。

## 九、当前代码逻辑与需要调整的流程

### 9.1 当前真实调用链

当前服务端 Run 的实际链路如下：

```text
POST /api/v1/ai/chat/threads/{thread_id}/runs/
        ↓
chat_sync/ai_api/views.py::CreateRunView.post
        ↓
chat_sync/ai_services/run_service.py::RunService.create_run
        ↓
冻结 ThreadPreferences、Capability、请求快照和 Run
        ↓
Celery 执行 chat_sync/ai_tasks/run_tasks.py::_execute_provider
        ↓
chat_sync/ai_services/context/context_builder.py::build_context_for_run
        ↓
读取 prefs.enabled_tools + capability.owned_tools + KB/deferred 条件
        ↓
chat_sync/ai_runtime/tools/composition.py::compose_enabled_tools
        ↓
manifest_entries(registry, composition.effective_names)
        ↓
保存 ChatTurnContextSnapshot.tool_manifest
        ↓
run_tasks.py::provider_tool_schemas
        ↓
Provider 发送 tools + tool_choice=auto
```

这条链路中，当前服务端工具来源主要是 `ChatThreadPreferences.enabled_tools`、Capability 和上下文自动挂载，尚未接入 `AIScenarioModelBinding.server_tool_scenarios`。

### 9.2 当前代码中的关键事实

| 文件 | 当前职责 | 与本需求的关系 |
|---|---|---|
| `ai_config/models.py::AIScenarioModelBinding` | 保存场景、模型、温度、Token、`ai_tool_scenarios` | 新增 `server_tool_scenarios` |
| `backoffice/serializers.py::AdminAIScenarioModelBindingSerializer` | 后台场景模型绑定读写和 JSON 校验 | 增加服务端工具字段和枚举校验 |
| `ai_config/admin.py::AIScenarioModelBindingAdmin` | Django Admin 列表/编辑入口 | 增加服务端工具可读字段和筛选展示 |
| `backoffice/views.py` | 后台 AI 模型/场景接口 | 保持现有入口，透传新字段 |
| `chat_sync/ai_api/views.py::CreateRunView` | 接收创建 Run 请求 | 不接受 Web 自行提交服务端工具列表 |
| `chat_sync/ai_services/run_service.py::RunService.create_run` | 冻结请求、偏好、Capability 和单活 Run | 保持 Run 创建职责，工具计算放到 Context Builder/Manifest Service |
| `chat_sync/ai_services/context/context_builder.py::build_context_for_run` | 构建上下文、工具清单和 ContextSnapshot | 接入场景模型绑定，替换当前 requested_tools 来源 |
| `chat_sync/ai_runtime/tools/registry.py` | 注册工具、生成 Schema、返回 Executor | 拆出服务端枚举交集校验，不能混入客户端枚举 |
| `chat_sync/ai_runtime/tools/composition.py` | 按请求、上下文和能力组合工具 | 改为接收服务端场景白名单，不接收客户端工具作为服务端候选 |
| `chat_sync/ai_services/tool_catalog_service.py` | 返回 P4 公共工具目录、校验 enabled_tools | 目录来源改为服务端枚举 + 场景绑定 + Registry |
| `chat_sync/ai_tasks/run_tasks.py::_execute_provider` | 使用 ContextSnapshot Manifest 调 Provider | 继续只使用冻结 Manifest，不重新计算工具 |
| `chat_sync/ai_models/context.py` | 保存 ContextSnapshot 和 `tool_manifest` | 保存来源列表、有效列表、过滤原因和 hash |
| `chat_sync/ai_runtime/tools/policy.py` | 工具执行策略和 Schema 校验 | 保留执行安全校验，不承担服务端/客户端工具枚举职责 |

### 9.3 需要调整的主流程

#### A. 场景/模型解析

当前 `RunService.create_run` 会保存 capability 和请求快照，但工具清单在后续 Context Builder 中重新从偏好和 Capability 推导。需要补充：

```text
Run.capability/scenario
        ↓
Provider/Model Route Resolver
        ↓
查询 AIScenarioModelBinding（scenario + model + is_active）
        ↓
读取 server_tool_scenarios
```

注意：模型解析仍由现有 `resolve_chat_route` 和 `AIScenarioModelBinding` 负责；本需求不改变 Pro 权益、模型选择、bootstrap 或 Provider Key 流程。

#### B. 服务端工具来源

当前 `build_server_tool_registry()` 同时注册了服务端工具和带客户端执行语义的工具。需要调整为：

```text
SparkServerToolName.values
        ↓
build_server_tool_registry()
        ↓
只允许服务端 Executor 对应的工具
```

客户端 `SparkToolName` 不进入 SparkService Registry，不参与服务端场景字段校验，也不参与 Provider Schema 生成。

#### C. Context Builder 工具计算

当前 `build_context_for_run()` 的 `requested_tools` 来源为：

```text
prefs.enabled_tools
+ capability.owned_tools
+ search_knowledge_bag（知识库条件）
+ DeferredToolService.active_names()
+ ask_user 开关
```

需要改为：

```text
model_binding.server_tool_scenarios
+ capability 允许的服务端工具
+ 上下文自动工具（仅限服务端枚举）
+ deferred 服务端工具
        ↓
统一 Manifest Service
        ↓
effective_names + filtered_tools
```

既有 `prefs.enabled_tools` 的兼容规则需明确：普通工具可作为场景白名单内的二次关闭项；不在 `server_tool_scenarios` 中的工具即使用户提交，也不得重新加入。

#### D. Provider 请求

当前 `_execute_provider()` 已从 `context.tool_manifest` 生成 `provider_tool_schemas`，这个边界应保留：

- Provider 不读取数据库中的 `ai_tool_scenarios`。
- Provider 不读取 Web 请求中的工具列表。
- Provider 不重新查询 Registry 计算工具。
- 只使用本次 Run 已冻结的 `tool_manifest`。

这样可保证重试、AskUser 恢复、Worker 切换时工具列表不漂移。

### 9.4 建议新增的统一服务

建议新增：

```text
chat_sync/ai_services/effective_tool_manifest_service.py
```

职责：

1. 根据 Run 的 capability、scenario 和 resolved model 查找 `AIScenarioModelBinding`。
2. 读取 `server_tool_scenarios`，拒绝未知服务端工具编码。
3. 与 `SparkServerToolName` 和 `build_server_tool_registry()` 求交集。
4. 合并服务端 Capability-owned、上下文自动挂载和已加载 deferred 工具。
5. 应用用户 Thread Preferences 的关闭项。
6. 应用模型 Tool Calling 能力、feature flag、Policy、权限和 required context。
7. 生成 `effective_tools`、`filtered_tools`、稳定顺序和 `manifest_hash`。
8. 将结果写入 `ChatTurnContextSnapshot`，供 Provider、Run 查询和 Web 展示复用。

禁止由以下模块各自重新实现一套工具判断：

- `tool_catalog_service.py`
- `context_builder.py`
- `run_tasks.py`
- Web 前端
- 后台管理前端

这些模块只能调用统一 Manifest Service 或读取已冻结结果。

### 9.5 数据库与接口调整清单

| 类型 | 文件/对象 | 需要调整 |
|---|---|---|
| 数据模型 | `ai_config/models.py::AIScenarioModelBinding` | 新增 `server_tool_scenarios` JSONField |
| 迁移 | `ai_config/migrations/` | 增加字段、默认值和数据迁移说明 |
| 后台序列化 | `backoffice/serializers.py` | 新增字段、服务端枚举校验、去重排序 |
| 后台展示 | `ai_config/admin.py`、`backoffice/views.py` | 增加服务端工具勾选/展示 |
| 服务端枚举 | `chat_sync/ai_runtime/tools/server_names.py` | 新增 `SparkServerToolName` |
| Registry | `chat_sync/ai_runtime/tools/registry.py` | 只暴露服务端注册工具给本需求链路 |
| Manifest | `chat_sync/ai_services/effective_tool_manifest_service.py` | 新增统一计算服务 |
| Context | `chat_sync/ai_services/context/context_builder.py` | 改用统一服务并冻结结果 |
| Snapshot | `chat_sync/ai_models/context.py` | 保存来源/有效/过滤列表和 hash |
| 公共目录 | `chat_sync/ai_services/tool_catalog_service.py` | 使用统一服务端枚举和场景来源 |
| Run 查询 | `chat_sync/ai_api/serializers.py`、`views.py`、`urls.py` | 增加 Run 工具快照查询接口 |
| Provider | `chat_sync/ai_tasks/run_tasks.py` | 仅消费 Snapshot Manifest，不重新计算 |
| 测试 | `chat_sync/tests/ai_runtime/`、`ai_services/`、`backoffice/` | 增加配置、过滤、快照和 Provider 一致性测试 |

### 9.6 明确不需要调整的流程

- 不修改 iOS、Android、HarmonyOS 的 `SparkToolName` 和工具执行代码。
- 不修改 WebSocket 认证、登录和会话隔离流程。
- 不修改 AI bootstrap、明文 `api_key`、Pro 用户权益和模型场景选择规则。
- 不让 Web 直接调用 Provider 或服务端 Executor。
- 不在 `CreateRunSerializer` 中增加“服务端工具列表”作为客户端可控入参。
- 不把客户端工具复制成服务端枚举。

## 十、实施阶段

### P0：契约确认

- 固化 `aiToolScenarios` 的字段和版本。
- 固化 Tool Registry Entry。
- 固化过滤原因码。
- 固化 Effective Tool Manifest DTO。
- 明确服务端枚举、客户端 `SparkToolName` 和 `execution_mode`。

### P1：统一解析器

- 实现 scenario/model 到工具绑定的解析。
- 将 Registry、Policy、Context、Provider 能力统一接入。
- 让 Thread 工具目录调用统一解析逻辑。
- 增加 manifest hash 和稳定排序。

### P2：Run 冻结与 Provider 接入

- Run 创建时生成 Manifest。
- ContextSnapshot 保存 Manifest。
- Provider 只接收 Manifest 生成的 schemas。
- 重试、暂停恢复、Worker 恢复复用同一 Manifest。

### P3：可见性接口与 Web 展示

- 增加场景工具预览接口。
- 增加 Run 工具快照接口。
- Web 展示 enabled/disabled/unavailable 和原因。
- 工具目录与 Tool Activity 使用同一 `tool_name/version/manifest_hash`。

## 十一、测试与验收

### 10.1 核心测试

- `aiToolScenarios` 中未知工具被标记 `not_registered`。
- 只有属于 `SparkServerToolName` 且有服务端 Executor 的工具进入 Web Provider Schema。
- 客户端 `SparkToolName` 工具不进入 Web Provider Schema。
- 模型不支持 Tool Calling 时，最终工具列表为空并返回 `model_unsupported`。
- 缺少 required context 的工具被过滤。
- Thread 关闭普通工具后不进入本次 Manifest。
- 强制工具不能被普通用户关闭。
- 同一 Run 重试前后 `manifest_hash` 不变。
- 同一 Run AskUser 暂停恢复前后工具列表不漂移。
- Provider request snapshot 与 Run 工具快照一致。
- Web 工具目录与 Run 工具快照的 enabled 工具名称可关联。

### 10.2 出口验收

- [ ] `aiToolScenarios` 只作为场景/模型绑定声明，不直接作为最终工具列表。
- [ ] `AIScenarioModelBinding` 具备独立的 `server_tool_scenarios` 配置字段。
- [ ] 后台可勾选维护服务端工具，且只能显示 `SparkServerToolName` 且有 Executor 的工具。
- [ ] 客户端 `SparkToolName` 工具不会写入服务端工具字段，也不会进入 Web Provider Schema。
- [ ] 不新增 `tool_type`、独立客户端工具字段或通过前端列表绕过服务端枚举。
- [ ] 服务端运行时统一计算 Effective Tool Manifest。
- [ ] 最终工具列表只包含已注册、可执行、通过 Policy 的服务端工具。
- [ ] Web 不会获得无法在服务端执行的 client-only 工具 Schema。
- [ ] 每个过滤结果都有稳定原因码和安全文案。
- [ ] Run 保存 `source_server_tool_scenarios`、`effective_tools`、`filtered_tools` 和 `manifest_hash`。
- [ ] Provider 实际请求只使用 Run Manifest 生成的 Tool Schema。
- [ ] 模型只能从已提供 Schema 中选择工具。
- [ ] 工具目录、Run 快照、Tool Activity 和跨端 Event 使用同一工具版本标识。
- [ ] DeepTutor 的 Registry/Composition/Schema/AgentLoop 语义测试迁移完成。
- [ ] 本工单没有修改移动端登录、客户端工具执行、AI bootstrap、明文 `api_key`、Pro 权益和模型选择流程。

## 十二、待确认问题

在创建实现工单前，需要确认：

1. `aiToolScenarios` 是否继续保留为 AI 模型配置字段，只是不再直接下发给前端和 Provider？
2. 是否确认新增 `server_tool_scenarios`，并将其作为服务端对话工具的唯一模型绑定来源？
3. 模型绑定工具是否采用工具名称 + 版本，还是只保存工具名称并由 Registry 补版本？
4. 场景绑定为 `required=true` 的工具，在不满足上下文时，是阻止 Run 创建，还是允许 Run 创建并标记不可用？
5. 用户关闭普通工具时，是否允许覆盖模型场景中的非强制工具？
6. 是否先只开放服务端只读工具和 `ask_user`，client-only 工具仅展示不可用原因？
7. 是否确认同时提供场景工具预览接口和 Run 有效工具快照接口？

---

工单结论：`aiToolScenarios` 负责声明“模型场景希望使用哪些工具”，新增的 `server_tool_scenarios` 负责声明“该模型场景允许使用哪些 SparkService 服务端工具”；运行时再根据 `SparkServerToolName`、服务端 Registry、Executor、Provider 能力、用户配置、权限和上下文计算最终候选工具列表。客户端 `SparkToolName` 完全独立，不参与服务端列表计算；模型只在最终 Tool Schema 中自主选择调用。这样既保留了 DeepTutor 的 Agent 语义，又让 SparkService 对每个 Run 的服务端工具边界可控、可解释、可审计、可跨端同步。
