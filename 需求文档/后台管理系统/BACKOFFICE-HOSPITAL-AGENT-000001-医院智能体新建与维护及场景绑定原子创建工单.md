# BACKOFFICE-HOSPITAL-AGENT-000001 医院智能体新建与维护及场景绑定原子创建工单

> 状态：待实施  
> 范围：`backoffice-web` 医院详情 / 智能体 Tab、`hospital_care`、`ai_config` 的既有数据模型引用  
> 不在范围：修改 `AIScenarioModelBinding` 模型、`save()` 默认绑定逻辑、AI Provider Key、AIModelCatalog、患者端 UI
> 医院知识库最终口径：`总领文档/医院智能体与医生工作台/医院知识库产品需求与落地方案.md`；历史工单：`BACKOFFICE-HOSPITAL-KNOWLEDGE-000001-医院知识库管理与智能体绑定及iOS会话异步获取工单.md`

## 1. 背景与目标

医院详情页的“智能体”Tab 已有列表、筛选和审核/暂停，但没有“新建智能体”入口。现有医生端 `PATCH /api/hospital/v1/me/agent/` 只能为当前登录医生创建/更新最近一条智能体，且需要前端先提供已有的 `scenario_binding_id`，不能满足平台医院管理员在医院后台创建多个医生智能体的场景。

本工单增加“新建智能体”和“智能体维护”表单。一次创建命令必须在同一事务内：

```text
选择已有基座模型 AIModelCatalog
        ↓
新建 AIScenarioModelBinding（identity=agent）
        ↓
新建 ClinicalAgentProfile（引用该 binding）
        ↓
可选：创建 ClinicalAgentKnowledgeBinding
        ↓
写 hospital + ai scenario binding 审计
```

最终的运行配置实体是既有 `ai_config.AIScenarioModelBinding`；`ClinicalAgentProfile` 是医院领域的医生、科室、公开资料、审核和患者可发现性档案。两者不是替代关系。

## 2. 冻结决策

1. 平台后台创建医院医生智能体；医生工作台保留“维护本人智能体 / 提交审核”，但不创建底层 Provider 或基座模型。
2. 新建时由表单选择一个已启用且已配置 Provider 的 `AIModelCatalog`，后端新建一条 `AIScenarioModelBinding`，而非复用医院外其他智能体的绑定。
3. 该绑定固定 `identity="agent"`、`scenario="chat"`、`is_default=false`。它是医院智能体的专属运行配置，不能抢占全局 Chat 默认模型。
4. 不改 [ai_config/models.py](/Users/hua/Documents/project/Reference/SparkService/ai_config/models.py:107) 中 `AIScenarioModelBinding` 的字段、约束、`save()` 或默认绑定切换逻辑；创建仍走其原有 `save()` 行为。
5. 创建初始状态为：`ClinicalAgentProfile.publication_status=draft`，`AIScenarioModelBinding.is_active=true`。未发布智能体不在患者目录出现；运行时只能通过医院会话显式引用 binding，不能因它 active 而成为全局默认。
6. 同一位医生允许拥有多个医院智能体；必须由 `ClinicalAgentProfile` 的唯一 UUID 区分。禁止继续以“取最近更新的一条”作为平台创建后的唯一选择规则。
7. 维护已发布智能体的运行配置或对外资料后，医院智能体自动回到 `review`，患者继续看最后已发布版本还是立即隐藏，由后续版本快照工单决定；本工单的首版采用“当前发布档案转 review 后从目录隐藏”的明确保守策略。

## 3. 页面改造

截图中的医院详情 `智能体` Tab 在筛选行右侧增加主按钮，仅拥有创建权限的管理员可见。

```text
智能体

[搜索智能体 / 医生] [全部状态⌄] [科室⌄]                         [+ 新建智能体]

智能体名称                 医生       科室       知识库  发布状态   操作
张医生 · 心血管咨询助手    张医生     心内科      2 个    已发布    维护 / 暂停
```

点击“新建智能体”打开全屏 Drawer（窄屏为独立页），避免在表格行内同时编辑医生资料、模型和患者侧文案。

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ 新建医院智能体                                                     [×]    │
│ 天长市中医院 · 创建后先保存为草稿，审核通过才对患者可见                    │
├──────────────────────────────────────────────────────────────────────────┤
│ 归属                                                                  │
│ 关联医生 *       [选择已激活医生⌄]                                      │
│ 服务科室 *       [选择该医院科室⌄]                                      │
│                                                                          │
│ 患者侧展示                                                              │
│ 智能体名称 *     [张医生 · 心血管咨询助手_______________________]       │
│ 公开简介         [面向患者的服务介绍____________________________]       │
│ 首次问候语       [您好，我是……__________________________________]       │
│ 服务边界 *       [健康咨询与就医指导；不提供确诊或处方____________]       │
│                                                                          │
│ AI 运行配置（创建新的专属场景绑定）                                     │
│ 基座模型 *       [选择已启用模型⌄] [查看模型能力]                        │
│ 温度             [0.2]       最大输出 Token [2048]                      │
│ 系统指令         [仅写该智能体工作规则；不得写入密钥________________]    │
│ 简介（内部）     [运行配置说明____________________________________]     │
│ 服务端工具       [多选：成员资料 / 健康资源 / ……]                        │
│                                                                          │
│ 知识库（可选）                                                          │
│ [选择已授权医院知识库⌄] [添加]                                          │
│ 已选：心内科就医指南（科室）  ×                                          │
│                                                                          │
│                                        [取消] [保存草稿]                 │
└──────────────────────────────────────────────────────────────────────────┘
```

维护使用同一个 Drawer，标题变为“维护智能体”。展示不可编辑的 `agent_id`、`scenario_binding_id`、创建人、发布时间、当前版本及审核状态；不展示 Provider Key、完整 Provider 地址、患者对话、个人记忆或其他医院知识库。

## 4. 字段映射与校验

| 表单字段 | 最终字段 | 必填 | 规则 |
| --- | --- | --- | --- |
| 关联医生 | `ClinicalAgentProfile.doctor_id` | 是 | 医生须属于当前医院、职工 active、DoctorProfile active |
| 服务科室 | `ClinicalAgentProfile.department_id` | 是 | 科室属于当前医院且为 active；首版允许医生跨本人主科室创建，但需审计 |
| 智能体名称 | `ClinicalAgentProfile.name` | 是 | 1–128 字；同医院同医生允许多个，但建议 UI 告警重名 |
| 公开简介/问候语/服务边界 | `public_summary/greeting/service_boundary` | 边界必填 | 服务边界不可为空；不得含密钥、患者身份或处方承诺 |
| 基座模型 | `AIScenarioModelBinding.model` | 是 | 只能选择 `AIModelCatalog.is_active=true` 且 Provider 可用的目录模型 |
| 身份/场景 | `identity/scenario` | 服务端固定 | 固定为 `agent/chat`，前端不提交可篡改枚举 |
| 温度、Token、位置 | `temperature/max_tokens/position` | 是 | 沿用现有 AI 绑定字段范围；position 由服务端计算当前 agent 绑定末位 |
| 系统指令、内部简介 | `system_provision/brief_description` | 否 | 归属新 binding，不能混写到 `service_boundary` |
| 工具、任务 | `ai_tool_scenarios/server_tool_scenarios/related_task_codes` | 否 | 使用现有 AI 配置的工具合法性校验；医院角色只能看到批准的候选项 |
| 知识库 | `ClinicalAgentKnowledgeBinding` | 否 | 只选经医院授权的 KnowledgeBase；同 agent + base 不可重复 |

请求不接受 `hospital_id`、`scenario`、`identity`、`is_default`、`is_active`、`publication_status`、`published_at`、`version` 等服务端推导字段。`is_default=false` 必须显式写入新 binding，避免创建医院智能体时意外改变平台默认 Chat 绑定。

## 5. 服务端接口契约

### 5.1 表单选项

```text
GET /api/admin/v1/hospital-care/hospitals/{hospital_id}/agent-form-options/
权限：api:hospital_care:agent:create
```

返回当前医院的可选 active 医生、active 科室、通过 Provider 可用性过滤后的模型、经授权可绑定的知识库、允许的工具/任务选项和建议默认值。不得让浏览器直接读取 `/api/admin/v1/ai/providers/` 以获得 Provider 配置。

### 5.2 新建

```text
POST /api/admin/v1/hospital-care/hospitals/{hospital_id}/agents/
Header: Idempotency-Key: <uuid>
权限：api:hospital_care:agent:create
```

请求示例（`model` 使用既有后台 AI 配置接口的模型 name，避免客户端猜测整数主键）：

```json
{
  "doctor_id": "uuid",
  "department_id": "uuid",
  "name": "张医生 · 心血管咨询助手",
  "public_summary": "由张医生团队维护的心血管健康咨询助手",
  "greeting": "您好，我是张医生团队的智能助手。",
  "service_boundary": "提供健康信息和就医指导，不提供确诊或处方。",
  "binding": {
    "model": "gpt-5.6-terra",
    "temperature": 0.2,
    "max_tokens": 2048,
    "system_provision": "你是心血管咨询助手……",
    "brief_description": "医院后台专属配置",
    "ai_tool_scenarios": [],
    "server_tool_scenarios": ["current_member"],
    "related_task_codes": []
  },
  "knowledge_bases": [
    {"knowledge_base_id": "uuid", "usage_scope": "department", "sort_order": 0}
  ]
}
```

成功响应返回 `agent_public(include_internal=true)`，并附加 binding 摘要：`id`、`bootstrap_name`、`model`、`is_active`、`is_default=false`。HTTP 201，仍使用项目标准 `{ code, msg, data }` 包裹。

### 5.3 维护

```text
GET   /api/admin/v1/hospital-care/agents/{agent_id}/
PATCH /api/admin/v1/hospital-care/agents/{agent_id}/
Header: Idempotency-Key: <uuid>
权限：api:hospital_care:agent:update
```

维护请求必须同时携带 `agent.version` 和 `binding.id`；若本次修改 binding，还需携带 binding 的 `updated_at`（或新增版本字段前使用该时间戳做条件更新）。返回 `AGENT_VERSION_CONFLICT` 时前端保留草稿，拉取最新配置后由操作者决定是否覆盖。

发布、驳回、暂停继续复用现有：

```text
POST /api/admin/v1/hospital-care/agents/{agent_id}/review/
```

它只变更医院智能体发布态，不负责新建 binding。

## 6. 原子服务设计

新增 `hospital_care.services.agent_provisioning_service.create_clinical_agent()`，作为后台创建唯一入口；View 只做序列化、权限和幂等包装。

```text
transaction.atomic()
  1. select_for_update(Hospital)，校验医院存在且不是 suspended
  2. 查 DoctorProfile / Department，校验均属于该医院且 active
  3. 查 AIModelCatalog，校验 is_active；校验该 company 存在 active Provider
  4. 校验工具列表，复用既有 server_tool_scenarios 校验器
  5. 创建 AIScenarioModelBinding：
       scenario=ScenarioKey.CHAT
       identity=IdentityKind.AGENT
       model=selected_model
       is_default=false
       is_active=true
       其余字段来自 binding 白名单
  6. 创建 ClinicalAgentProfile：引用新 binding，publication_status=draft
  7. 创建已授权的 ClinicalAgentKnowledgeBinding
  8. 写入 hospital.agent.create 和 admin.ai.scenario_binding.create 审计
commit 后返回完整摘要
```

不直接复用 `backoffice.views.AdminAIScenarioBindingListCreateView`：它是 HTTP View，不是医院领域服务。可复用其 Serializer 的字段校验逻辑，但应提炼共享校验/构造函数，避免 `hospital_care -> backoffice.views` 的反向依赖。

如果第 5–7 步任一步失败，事务整体回滚：不留下孤立 `AIScenarioModelBinding`、半成品 `ClinicalAgentProfile` 或知识库绑定。相同幂等键和相同请求返回首次成功结果；相同键不同请求返回 `IDEMPOTENCY_CONFLICT`。

## 7. 新增权限、错误码与审计

新增 RBAC：

```text
button:hospital_care:agent:create
button:hospital_care:agent:update
api:hospital_care:agent:create
api:hospital_care:agent:read
api:hospital_care:agent:update
```

| 错误码 | 条件 | 页面处理 |
| --- | --- | --- |
| `AGENT_DOCTOR_INVALID` | 医生不属于医院、停用或档案未激活 | 定位“关联医生”，刷新选项 |
| `AGENT_DEPARTMENT_INVALID` | 科室无效、停用或跨医院 | 定位“服务科室” |
| `AGENT_BASE_MODEL_UNAVAILABLE` | 模型停用或无可用 Provider | 定位“基座模型”，不泄露凭证详情 |
| `AGENT_KNOWLEDGE_BASE_FORBIDDEN` | 知识库未授权给医院 | 从已选列表移除并显示合规提示 |
| `AGENT_VERSION_CONFLICT` | 维护并发冲突 | 拉取最新，保留本地草稿 |
| `IDEMPOTENCY_CONFLICT` | 同键不同内容 | 禁止静默重试 |

审计至少记录：医院 ID、agent ID、binding ID、基座模型 ID、操作者、前后发布态、知识库 ID 列表摘要、request ID。不得记录系统指令全文、患者信息、Provider Key、完整 Provider URL 或知识库正文。

## 8. 与 AI 运行时的衔接边界

本工单负责把医院智能体的专属运行配置**落到** `AIScenarioModelBinding`，但不应假定“创建绑定后现有 Chat Run 自动选中它”。当前 AI Runtime 默认按全局 `ScenarioKey.CHAT` 解析默认 binding；后续需新增医院会话解析：

```text
ChatThread.hospital_binding.agent.scenario_binding
  -> 医院会话专属 model / temperature / system_provision / tools
  -> ClinicalAgentKnowledgeBinding 的可用知识库
```

该运行时接入应作为后续独立工单实施。没有该接入前，后台可以创建和发布智能体档案，但必须在内部标注“运行时专属配置待接入”，不能宣称患者对话已使用该基座模型和知识库。

## 9. 验收

1. 智能体 Tab 有权限用户可见 `+ 新建智能体`，无权限用户不见按钮且 API 返回 403。
2. 选择有效医生、科室、模型并保存后，同时得到一条 `ClinicalAgentProfile` 与一条 `AIScenarioModelBinding(identity=agent)`；Profile 的 FK 指向该新 binding。
3. 新 binding 始终 `scenario=chat`、`is_default=false`；创建不改变任意已有全局默认 binding。
4. Provider 未配置、模型/医生/科室停用、跨医院知识库、重复幂等键等失败时，数据库没有残留绑定或档案。
5. 新智能体默认草稿，不在患者端目录展示；审核发布后才被 `published_agents()` 返回。
6. 维护已发布智能体后转 `review`，并保留可审计的变更记录。
7. 一位医生新建两个不同智能体时，列表均存在、可独立维护和审核；不再由“最近更新”误覆盖另一条。
8. 审计与响应中没有 Provider Key、患者内容、知识库正文或系统指令全文。

## 10. 实施文件清单（目标）

| 位置 | 变更 |
| --- | --- |
| `hospital_care/api/backoffice/urls.py` | 增加 agent form options、create、detail/update 路由 |
| `hospital_care/api/backoffice/serializers.py` | 新建/维护表单 DTO 与嵌套 binding DTO |
| `hospital_care/api/backoffice/views.py` | 调用 provisioning service 的 APIView |
| `hospital_care/services/agent_provisioning_service.py` | 原子创建、维护、模型/知识库校验 |
| `hospital_care/selectors/backoffice_hospital_catalog.py` | 表单 options、agent detail 查询 |
| `hospital_care/exceptions.py` | 新业务错误码映射 |
| `backoffice/rbac.py` | 创建/读取/更新权限种子 |
| `backoffice-web/src/api/modules/hospitalCare.ts` | options、create、detail、update API 与类型 |
| `backoffice-web/src/views/hospital-care/HospitalDetailView.vue` | `+ 新建智能体`、维护入口、Drawer 状态 |
| `backoffice-web/src/components/hospital-care/ClinicalAgentFormDrawer.vue` | 可复用的新建/维护表单 |
| `hospital_care/tests/` | 事务回滚、默认绑定不变、权限、并发、幂等与发布目录回归 |

本工单不创建 migration：`ClinicalAgentProfile` 已经引用既有 `AIScenarioModelBinding`，所需字段均已存在；只有后续决定为 binding 增加独立乐观锁版本字段时，才另开 migration 工单。
