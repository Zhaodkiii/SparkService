# CHAT-AI-031 服务端工具场景为空排查与后台配置链路修复工单

> 创建日期：2026-08-27  
> 状态：待排查与联调，未开始实现  
> 优先级：P0  
> 关联工单：CHAT-AI-030、CHAT-AI-029  
> 范围：AI 场景配置、模型绑定、服务端工具配置和后台管理系统  
> 约束：本工单只记录问题、证据和修复方案；未授权前不得修改移动客户端、AI bootstrap、明文 `api_key`、Pro 权益或模型选择流程。

## 一、问题现象

后台 AI 场景配置中的“服务端工具场景（`server_tool_scenarios`）”确认是**选项列表为空**，不是已选值为空。必须优先排查选项接口和前端数据源，不应先做历史数据回填。

1. **当前确认现象**：后台没有拿到服务端工具选项，或前端将服务端选项响应过滤成空数组。
2. **次级现象**：选项列表恢复后，才再判断当前 `AIScenarioModelBinding.server_tool_scenarios` 已选值是否为空。

两种现象不能用同一个修复判断；本工单当前优先级是“选项列表接口/注册/渲染链路”。

## 二、当前代码证据

### 2.1 数据模型与迁移

文件：`ai_config/models.py::AIScenarioModelBinding`

```python
server_tool_scenarios = models.JSONField(
    default=list,
    blank=True,
    db_comment="场景模型绑定的 SparkService 服务端工具场景编码列表",
)
```

迁移：`ai_config/migrations/0005_aiscenariomodelbinding_server_tool_scenarios.py`

新增字段默认值是 `[]`。因此，历史模型绑定如果没有显式保存过服务端工具，显示为空是预期数据库结果；`ai_tool_scenarios` 不会自动复制到该字段。

### 2.2 后台接口存在两套工具来源

文件：`backoffice/views.py`

```text
AdminAIToolOptionsView
  → 返回客户端/通用 SparkToolName

AdminAIServerToolOptionsView
  → 返回 SparkServerToolName + 服务端 Registry 元数据
```

`server_tool_scenarios` 必须使用 `AdminAIServerToolOptionsView`，不能使用返回客户端 `SparkToolName` 的接口。

后台路由已确认存在：

```text
GET /ai/tool-options/         → AdminAIToolOptionsView（客户端 SparkToolName）
GET /ai/server-tool-options/  → AdminAIServerToolOptionsView（服务端工具）
```

因此本问题首先要确认后台页面是否请求了 `ai/server-tool-options/`。如果页面请求的是 `ai/tool-options/`，则属于数据源接错，不是服务端枚举为空。

### 2.3 后台 Serializer 已有字段

文件：`backoffice/serializers.py::AdminAIScenarioModelBindingSerializer`

当前 `fields` 已包含：

```text
ai_tool_scenarios
server_tool_scenarios
```

并已有 `validate_server_tool_scenarios()`，调用：

```text
chat_sync/ai_runtime/tools/server_tool_config.py
```

因此需要重点检查后台前端是否真正完成字段的表单绑定、请求提交和响应回填，而不是只看后端 Serializer。

### 2.4 服务端选项由枚举和 Registry 共同生成

文件：

```text
chat_sync/ai_runtime/tools/server_names.py
chat_sync/ai_runtime/tools/server_tool_config.py
chat_sync/ai_runtime/tools/registry.py
```

当前服务端枚举包括：

```text
ask_user
search_knowledge_bag
get_current_member
query_member_profile
list_member_health_sources
get_health_resource_context
read_source
```

`list_admin_server_tool_options()` 会检查每个枚举项是否在 Registry 中存在 Executor，并返回 `has_executor`。如果后台只渲染 `has_executor=true`，Registry 注册异常也会被误显示为空。

### 2.5 场景预览与 Run 已读取该字段

文件：`ai_config/views.py`

场景预览已读取：

```python
binding.server_tool_scenarios
```

文件：`chat_sync/ai_services/effective_tool_manifest_service.py`

Run Manifest 已读取：

```python
source_names = normalize_tool_names(binding.server_tool_scenarios)
```

文件：`chat_sync/ai_services/context/context_builder.py`

最终会将服务端工具来源写入 ContextSnapshot。若绑定字段为空，Run 不会从客户端 `SparkToolName` 自动补工具。

## 三、最可能原因与验证方案

### 3.0 当前确认后的优先排查路径

由于现象已经确认是“选项列表为空”，排查顺序调整为：

```text
浏览器 Network 请求 URL
        ↓
AdminAIServerToolOptionsView 响应状态/数组长度
        ↓
SparkServerToolName 枚举数量
        ↓
build_server_tool_registry() 是否抛异常
        ↓
每项 has_executor 是否被前端过滤
        ↓
场景模型绑定字段回填
```

在选项列表恢复前，不处理历史 `server_tool_scenarios=[]` 数据迁移。

### 原因 1：后台仍调用客户端工具选项接口（最高优先级）

后台如果调用 `AdminAIToolOptionsView`，返回的是客户端 `SparkToolName`；如果前端又按服务端字段规则过滤，最终可能显示为空。

验证：检查浏览器请求是否为：

```text
/ai/server-tool-options/
```

解决方向：服务端字段固定使用 `AdminAIServerToolOptionsView`，客户端工具接口不得复用。

### 原因 2：服务端选项接口未被后台前端接入

后端路由和 View 已存在，但后台页面可能没有调用该接口，或接口基路径拼接错误导致 404/401 后被前端降级为空数组。

验证：记录 HTTP 状态码、响应 body、权限信息和前端异常处理。

解决方向：明确接口契约，非 2xx 不得静默转为空数组，应显示“服务端工具列表加载失败”。

### 原因 3：服务端枚举/Registry 选项生成异常

`AdminAIServerToolOptionsView` 调用 `list_admin_server_tool_options()`，该函数会遍历 `SparkServerToolName` 并查询 `build_server_tool_registry()`。枚举为空、导入异常或 Registry 构建失败都可能造成列表为空或请求失败。

验证：直接请求接口；检查响应数组长度、`has_executor` 和服务端日志。

解决方向：接口必须返回枚举项及 `has_executor`；不能在异常时静默返回 `[]`。

### 原因 4：前端只渲染 `has_executor=true` 且全部被过滤

当前服务端枚举项若未正确注册 Executor，会返回 `has_executor=false`。前端若只保留 `has_executor=true`，可能显示空列表。

验证：对比接口原始响应和组件最终列表长度。

解决方向：无 Executor 项显示“暂不可配置”及原因，不得静默丢弃。

### 原因 5：历史数据未回填

新增 JSONField 后，已有 `AIScenarioModelBinding` 行默认为 `[]`。原有 `ai_tool_scenarios` 可能包含客户端工具，不能无条件复制。

验证：查询目标场景/模型绑定的 `server_tool_scenarios` 实际数据库值。

方案：

- 不做无条件复制。
- 对已确认的服务端工具进行人工配置或受控一次性迁移。
- 客户端工具拒绝写入服务端字段。

### 原因 6：后台表单没有提交或回填字段

可能情况：

- 表单缺少 `server_tool_scenarios` 控件。
- 初始值取了 `ai_tool_scenarios`。
- PATCH/POST 请求体没有该字段。
- 保存响应被旧对象覆盖。
- value 使用显示名称而不是工具 raw value。

验证：对比场景绑定 GET、保存请求体、保存响应和刷新后的 GET。

方案：前端使用独立状态 `server_tool_scenarios`，value 必须是 `SparkServerToolName` raw value。

### 原因 7：Registry/Executor 校验导致选项被前端隐藏

枚举项存在但 Registry 没有对应 Executor，接口会返回 `has_executor=false`。前端若静默过滤，就会显示空列表。

验证：直接调用 `AdminAIServerToolOptionsView`，检查每一项 `has_executor`，并检查 `build_server_tool_registry()` 导入日志。

方案：后台展示不可配置项及原因；保存时返回明确的 `server_tool_executor_missing`，禁止静默丢弃。

### 原因 8：数据库迁移未应用

验证：

```text
python manage.py showmigrations ai_config
```

确认 `0005_aiscenariomodelbinding_server_tool_scenarios` 已应用。未应用通常应报数据库错误，不能被误判为空数组。

## 四、正确后台链路

```text
打开模型编辑
  → 请求 AdminAIServerToolOptionsView
  → 返回 SparkServerToolName + Registry 元数据
  → 请求场景模型绑定详情
  → 回填 server_tool_scenarios
  → 用户勾选服务端工具
  → POST/PATCH 提交 server_tool_scenarios
  → Serializer 校验枚举、Registry、Executor
  → 保存 AIScenarioModelBinding
  → GET 回填相同字段
  → Run 创建读取同一字段
  → Effective Tool Manifest
  → Provider Tool Schema
```

## 五、文件级调整清单

| 文件/模块 | 当前状态 | 需要确认或调整 |
|---|---|---|
| `ai_config/models.py` | 已有字段 | 确认字段部署一致，不重复创建 |
| `ai_config/migrations/0005_*.py` | 已有迁移 | 确认各环境已应用 |
| `backoffice/views.py::AdminAIToolOptionsView` | 客户端工具接口 | 不得用于服务端字段 |
| `backoffice/views.py::AdminAIServerToolOptionsView` | 服务端工具接口 | 作为唯一服务端选项入口 |
| `backoffice/serializers.py` | 已有字段和校验 | 核对请求提交/响应回填 |
| `chat_sync/ai_runtime/tools/server_names.py` | 服务端枚举 | 维护服务端白名单 |
| `chat_sync/ai_runtime/tools/server_tool_config.py` | 字段校验 | 保持拒绝客户端、未知和无 Executor 工具 |
| `chat_sync/ai_runtime/tools/registry.py` | Registry | 核对服务端 Executor 注册一致性 |
| `chat_sync/ai_services/effective_tool_manifest_service.py` | Run 解析 | 只读取已保存服务端字段 |
| `chat_sync/ai_services/context/context_builder.py` | Snapshot 构建 | 不从客户端工具补服务端工具 |
| 后台 AI 模型编辑前端 | 待核实 | 使用服务端接口和独立字段 |

## 六、接口验收样例

服务端工具选项应能返回：

```json
[
  {"value": "ask_user", "label": "询问用户", "has_executor": true},
  {"value": "read_source", "label": "读取资料", "has_executor": true}
]
```

场景模型绑定应返回：

```json
{
  "ai_tool_scenarios": ["get_current_location"],
  "server_tool_scenarios": ["ask_user", "read_source"]
}
```

Run 快照应返回：

```json
{
  "source_server_tool_scenarios": ["ask_user", "read_source"],
  "effective_tools": ["ask_user", "read_source"],
  "manifest_hash": "sha256:..."
}
```

## 七、排查顺序

1. 查询目标绑定的 `server_tool_scenarios` 数据库值。
2. 确认 `0005` 迁移已应用。
3. 直接请求 `AdminAIServerToolOptionsView`，检查数组长度和 `has_executor`。
4. 检查后台前端是否误用 `AdminAIToolOptionsView`。
5. 检查 GET 回填、PATCH/POST 请求体、保存响应和刷新 GET。
6. 创建测试 Run，检查 `ContextSnapshot.tool_manifest_source`。
7. 检查 Provider request snapshot 与 Run Manifest 是否一致。

## 八、测试与验收

- 服务端选项接口不返回客户端 `SparkToolName`。
- 后台可以加载服务端工具选项并正确回填已选值。
- `server_tool_scenarios` 可以保存、刷新后保持一致。
- 客户端工具不会自动复制到服务端字段。
- 未知工具、客户端工具和无 Executor 工具保存时返回明确错误。
- 历史空数组不会被静默解释为“全部工具启用”。
- Run 的 `source_server_tool_scenarios` 与绑定记录一致。
- Provider Schema 与 Run Manifest 一致。
- 不修改移动客户端、AI bootstrap、明文 `api_key`、Pro 权益和模型选择流程。

## 九、待确认事项

1. 后台 Network 中实际请求是否为 `/ai/server-tool-options/`？
2. 该接口返回的是 2xx 空数组、非 2xx，还是有数据但前端渲染为空？
3. 是否允许后台展示 `has_executor=false` 的服务端枚举项并标记不可配置？
4. 历史绑定是否需要人工配置初始服务端工具？
5. `ask_user` 是否由每个模型绑定显式勾选，还是作为服务端对话默认工具？

---

工单结论：当前已确认是“服务端工具选项列表为空”，最高优先级不是历史数据回填，而是确认后台是否调用 `/ai/server-tool-options/`、接口是否返回数据、`SparkServerToolName`/Registry 是否成功生成选项，以及前端是否错误过滤 `has_executor`。只有选项列表恢复后，才继续排查 `server_tool_scenarios` 已选值。客户端 `SparkToolName` 不得作为服务端工具来源。
