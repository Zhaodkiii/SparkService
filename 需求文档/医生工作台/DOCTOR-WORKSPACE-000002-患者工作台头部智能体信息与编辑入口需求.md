# DOCTOR-WORKSPACE-000002 患者工作台头部智能体信息与编辑入口需求

> 状态：需求确认稿  
> 更新时间：2026-09-03  
> 适用项目：SparkService / chat-web  
> 交付范围：需求与落地设计，不修改业务代码  
> 关联工单：DOCTOR-WORKSPACE-000001 患者工作台与患者基础资料需求确认工单

## 1. 需求结论

患者工作台头部必须同时回答两个问题：

1. 医生当前正在查看哪一位患者。
2. 当前医生使用哪一个医生智能体为该患者提供服务。

现有患者信息头只展示患者身份、服务状态和重点患者标记，缺少智能体上下文。新增“当前服务智能体”公共头部，并在信息条右侧提供“编辑智能体”按钮。

该公共头部位于患者列表和患者信息之上，横向覆盖“患者列表 + 患者工作台主区”的患者业务区域。患者列表仍保持当前独立一列，不把患者列表移动到患者信息卡内部，也不把智能体信息复制到每一位患者卡片。

点击“编辑智能体”后，不跳转离开患者工作台；在当前页面上方打开模态弹窗，复用已有 DoctorAgentForm 的字段、校验、保存草稿、提交审核和版本冲突处理。关闭弹窗后仍停留在当前患者与当前滚动位置。

本工单不新建智能体数据模型、不新建第二套编辑表单、不改变会话与智能体的绑定关系。

## 2. 当前实现事实与偏差

| 项目 | 当前实现 | 本工单目标 | 偏差 |
| --- | --- | --- | --- |
| 患者工作台头部 | PatientIdentityAndProfile 只展示患者信息 | 同时展示患者身份与当前服务智能体 | 缺少智能体信息区 |
| 智能体读取 | GET /api/hospital/v1/me/agent/ 已存在 | 直接复用 | 无需新增接口 |
| 智能体编辑 | DoctorAgentForm 为独立整页组件 | 同一表单可在弹窗中打开 | 组件当前包含整页容器和自身请求，需要支持嵌入模式 |
| 智能体保存 | PATCH /api/hospital/v1/me/agent/ 已存在 | 直接复用 | 无需新增保存接口 |
| 提交审核 | POST /api/hospital/v1/me/agent/submit/ 已存在 | 直接复用 | 无需新增流程 |
| 并发控制 | version 与 AGENT_VERSION_CONFLICT 已存在 | 弹窗沿用 | 无需另建锁机制 |
| 患者缓存 | 已按 hospital_id + doctor_id + member_id + module 隔离 | 智能体信息不进入患者级缓存 | 智能体是医生级数据，不能复制进每位患者缓存 |

## 3. 信息归属与页面语义

### 3.1 页面层级与列布局

患者工作台采用以下空间层级：

~~~text
医生工作台内容区
├── 当前服务智能体公共头部（位于患者列表、患者信息之上）
└── 患者业务区
    ├── 患者列表（保持原样，独立一列）
    ├── 患者信息与工作台主区
    └── 患者辅助信息 / 会话抽屉
~~~

公共头部只出现一次，不随患者列表滚动，不出现在患者卡片内。选择患者后，下面的患者信息头才展示具体患者。

### 3.2 患者身份区

患者身份仍是页面主标题，保留：

- 患者头像。
- 患者姓名。
- 性别、年龄。
- 患者编号。
- 服务状态。
- 重点患者标记。

患者基础资料保持只读。本工单不增加患者资料编辑能力。

### 3.3 当前服务智能体区

在患者列表和患者信息之上新增一条独立的智能体信息条，默认展示：

- 智能体名称。
- “医生智能体”固定标识。
- 维护医生姓名与职称。
- 所属科室。
- 发布状态。
- 对外简介 public_summary；最多一行，超出省略。
- 已关联知识库数量；只展示数量，不在头部展开具体知识库。
- “编辑智能体”按钮。

智能体头像默认优先使用医生头像；医生无头像时使用智能体名称首字或统一 AI 图标。

### 3.3 智能体选择规则

头部展示的是当前登录医生通过现有 doctor_agent 规则取得的智能体，也就是 GET /api/hospital/v1/me/agent/ 返回的对象。

它不是患者级智能体副本，也不根据患者会话列表中的任意一条历史会话切换。原因如下：

- 患者工作台头部表达当前医生的服务能力。
- 历史会话可能绑定旧版本或旧智能体，仍由会话列表和会话抽屉按各自 agent 快照展示。
- 打开某条会话时，不覆盖页面头部的当前服务智能体。
- 新建对话继续使用服务端现有规则，自动绑定当前医生可用且已发布的智能体。

## 4. 页面结构

页面空间顺序调整为：

1. 当前服务智能体公共头部，横向位于患者列表和患者信息之上。
2. 患者列表独立列，保持现有搜索、筛选、排序和卡片结构。
3. 患者信息头。
4. 患者基础资料。
5. AI 总结（系统生成）。
6. 风险评估（现有风险工具）。
7. 患者会话列表。
8. 右侧患者辅助信息或会话抽屉。

智能体信息必须位于首屏公共头部，不能放到患者卡片、AI 总结、右侧辅助栏或会话列表内部。

## 5. 编辑交互流程

### 5.1 打开编辑表单

1. 医生进入患者工作台。
2. 页面独立读取当前医生智能体。
3. 读取成功后展示智能体信息条。
4. 医生点击“编辑智能体”。
5. 页面打开居中模态弹窗。
6. 弹窗使用当前已读取的智能体作为初始值；若数据不存在或已过期，再调用现有 getAgent 刷新。
7. 背景页面保留，但禁止点击和滚动穿透。
8. 焦点进入弹窗标题或第一个可编辑字段。

### 5.2 表单内容

弹窗复用现有 DoctorAgentForm 的业务字段：

| 字段 | 行为 |
| --- | --- |
| 公开名称 | 可编辑，必填 |
| 对外简介 | 可编辑 |
| 欢迎语 | 可编辑 |
| 服务边界 | 可编辑；提交审核前必填 |
| 所属科室 | 沿用现有规则，只读展示 |
| 场景绑定 ID | 沿用现有编辑规则 |
| 绑定知识库 | 沿用现有只读列表 |
| 发布状态 | 弹窗头部展示 |
| 保存草稿 | 调用现有更新接口 |
| 提交审核 | 调用现有提交接口 |

“复用已有表单”指复用同一字段组件、状态处理和提交函数，不允许复制一份 PatientAgentEditForm 形成双维护源。

### 5.3 保存成功

保存成功后：

- 使用 PATCH 返回的新 DoctorAgentDTO 更新共享智能体状态。
- 头部立即刷新名称、简介、科室、状态和知识库数量。
- 弹窗默认保持打开，并显示“保存成功”，便于继续提交审核。
- 医生主动点击完成或关闭后，返回原患者工作台。
- 不刷新整个页面。
- 不清空患者资料、患者会话、AI 总结和风险评估缓存。
- 不改变当前打开的患者和会话抽屉。

### 5.4 提交审核成功

- 使用提交接口返回值更新头部。
- 发布状态切换为“审核中”时，表单按现有 readOnly 规则禁用。
- 弹窗可关闭，患者工作台继续可用。

### 5.5 关闭与未保存内容

- 未修改时，点击关闭按钮、遮罩或 Escape 可直接关闭。
- 已修改且未保存时，弹出二次确认：“尚有未保存修改，确定关闭吗？”
- 选择继续编辑则保留所有输入。
- 选择放弃修改则恢复到最近一次服务端成功响应。
- 不把未保存草稿写入患者工作台缓存。

## 6. 状态设计

| 状态 | 头部表现 | 编辑入口 |
| --- | --- | --- |
| loading | 智能体信息条骨架屏，不阻塞患者资料 | 禁用 |
| ready | 展示完整智能体摘要 | 可用 |
| empty | “当前医生尚未分配智能体” | 不显示编辑；可保留“前往我的智能体”入口 |
| error | 保留患者工作台，信息条显示加载失败与重试 | 禁用至重试成功 |
| draft | 状态标记“草稿” | 可编辑 |
| review | 状态标记“审核中” | 可打开查看，字段按现有规则只读 |
| published | 状态标记“已发布” | 可编辑，保存后的发布语义沿用现有服务端 |
| disabled | 状态标记“已停用” | 是否可编辑沿用服务端权限，不允许前端假定可发布 |

智能体接口失败不得阻塞患者资料、会话列表、AI 总结、风险评估或已打开会话的使用。

## 7. 数据与缓存方案

### 7.1 数据源

继续使用：

- GET /api/hospital/v1/me/agent/
- PATCH /api/hospital/v1/me/agent/
- POST /api/hospital/v1/me/agent/submit/

不要求患者工作台聚合接口重复返回 agent，不要求修改 PatientWorkspaceDTO。

### 7.2 状态作用域

智能体状态作用域为：

~~~text
hospital_id + doctor_id + agent_id
~~~

不得按 member_id 保存。切换患者时继续使用同一份当前医生智能体数据，不重复请求。

### 7.3 推荐前端状态组织

在医生工作台共享层维护 DoctorAgentState，患者工作台头部与“我的智能体”页面共同消费：

~~~text
DoctorAgentState
├── status: idle | loading | ready | empty | error
├── data: DoctorAgentDTO | null
├── error: string | null
├── fetchedAt: number | null
├── refresh()
├── update(payload)
└── submit(version)
~~~

若本期不抽取共享 Context，最低限度也必须让弹窗接收 initialAgent 和 onSaved，避免弹窗保存后头部仍显示旧数据。

### 7.4 刷新策略

- 首次进入医生工作台时加载一次。
- 切换患者不重新加载。
- 打开编辑弹窗时，若内存中已有数据先立即展示，再后台校验。
- 保存或提交成功时以响应对象覆盖内存数据。
- 浏览器重新载入后重新请求。
- 医生身份、医院身份变化时清空旧智能体状态并重新加载。

## 8. 服务端契约复用

### 8.1 读取响应

现有 DoctorAgentDTO 已能满足头部展示：

~~~text
id
hospital_id
name
public_summary
greeting
service_boundary
publication_status
published_at
doctor.id
doctor.display_name
doctor.title
doctor.avatar_url
department.id
department.name
version
knowledge_bindings[]
~~~

知识库数量按 knowledge_bindings 中 status 为 active 的项目统计；不新增 count 字段也可完成演示。

### 8.2 更新请求

继续提交 DoctorAgentUpdatePayload：

~~~text
name
public_summary
greeting
service_boundary
department_id
scenario_binding_id
version
~~~

必须携带当前 version。服务端返回 AGENT_VERSION_CONFLICT 时，弹窗不得静默覆盖其他页面或其他设备已保存的内容。

### 8.3 并发冲突

推荐交互：

1. 保留医生当前输入。
2. 显示“智能体资料已在其他位置更新”。
3. 提供“加载最新内容”和“取消”两个动作。
4. 加载最新内容前再次确认，因为该动作会覆盖当前未保存输入。
5. 不自动重复 PATCH。

当前 DoctorAgentForm 在冲突后自动重新读取并 applyAgent，会覆盖本地输入。实施本工单时应把冲突处理提升为显式确认，以避免弹窗中的长文本丢失。

## 9. 前端组件落地方案

### 9.1 组件拆分

建议在不复制业务逻辑的前提下拆分：

~~~text
PatientWorkspacePage
├── CurrentAgentHeader（公共头部，位于患者列表和患者信息之上）
│   └── AgentEditDialog
│       └── DoctorAgentForm
└── PatientWorkspaceColumns
    ├── PatientListPanel（保持原样，独立一列）
    ├── PatientWorkspaceMain
    │   └── PatientIdentityAndProfile
    └── PatientAsidePanel

DoctorAgentPage
└── DoctorAgentForm（同一表单的 page 模式）
~~~

DoctorAgentForm 新增展示模式参数，仅控制外壳，不改变字段和提交逻辑：

~~~tsx
type DoctorAgentFormProps = {
  mode?: "page" | "dialog";
  initialAgent?: DoctorAgentDTO | null;
  onSaved?: (agent: DoctorAgentDTO) => void;
  onSubmitted?: (agent: DoctorAgentDTO) => void;
  onClose?: () => void;
};
~~~

以上代码仅为实施结构示例，不是本工单中的代码变更。

### 9.2 当前智能体信息条示例

~~~tsx
<CurrentAgentHeader
  agent={agentState.data}
  status={agentState.status}
  onEdit={() => setAgentEditorOpen(true)}
  onRetry={agentState.refresh}
/>
~~~

### 9.3 弹窗语义

弹窗必须具备：

- role=dialog。
- aria-modal=true。
- aria-labelledby 指向“编辑医生智能体”。
- 打开后焦点进入弹窗。
- Tab 焦点不能越出弹窗。
- Escape 按未保存状态规则关闭。
- 关闭后焦点回到“编辑智能体”按钮。
- 提交中禁用重复提交。

## 10. 关键文件位置

| 职责 | 当前文件 | 本工单影响 |
| --- | --- | --- |
| 患者工作台主区 | chat-web/components/doctor/PatientWorkspaceMain.tsx | 保持患者信息、资料、会话和总结内容；不承载公共智能体头部 |
| 患者工作台布局 | chat-web/components/doctor/PatientWorkspacePage.tsx | 增加位于患者列表和患者信息之上的公共智能体头部；患者列表仍为独立一列 |
| 患者状态 | chat-web/context/PatientWorkspaceContext.tsx | 不放智能体数据，避免患者级重复缓存 |
| 智能体表单 | chat-web/components/doctor/DoctorAgentForm.tsx | 抽取可嵌入模式；保持同一字段与提交逻辑 |
| 我的智能体页面 | chat-web/app/(doctor)/doctor/agent/page.tsx | 继续复用同一表单的 page 模式 |
| 医院 API 客户端 | chat-web/lib/api/hospital-api.ts | 复用 getAgent、updateAgent、submitAgent |
| DTO | chat-web/types/hospital.ts | 复用 DoctorAgentDTO 与 DoctorAgentUpdatePayload |
| 页面样式 | chat-web/app/globals.css | 新增信息条与弹窗外壳样式，不复制表单字段样式 |
| 服务端读取/更新 | hospital_care/api/staff/views.py | 现有 StaffAgentView 可复用 |
| 服务端路由 | hospital_care/api/staff/urls.py | 现有 me/agent 路由可复用 |
| 服务端序列化 | hospital_care/api/staff/serializers.py | 现有 DoctorAgentUpdateSerializer 可复用 |
| 服务端展示结构 | hospital_care/api/presenters.py | 现有 agent_public(include_internal=True) 可复用 |
| 智能体查询 | hospital_care/selectors/doctor_workspace.py | 现有 doctor_agent 可复用 |
| 智能体保存 | hospital_care/services/agent_service.py | 现有 upsert_doctor_agent 可复用 |
| 智能体模型 | hospital_care/models/agent_profiles.py | 不修改 ClinicalAgentProfile 结构 |

## 11. 异常边界

| 异常 | 页面处理 |
| --- | --- |
| 智能体读取失败 | 信息条局部报错并可重试；患者工作台其余模块继续可用 |
| 未分配智能体 | 显示空态，不伪造智能体；新建对话继续以服务端校验结果为准 |
| 智能体审核中 | 允许打开查看；字段按现有 readOnly 规则禁用 |
| 智能体下架或停用 | 状态立即展示；不在前端伪装为已发布 |
| 保存网络失败 | 弹窗不关闭，保留输入并允许重试 |
| 版本冲突 | 不自动覆盖本地输入，提示加载最新版本 |
| 当前医生身份失效 | 关闭弹窗，走医生登录/权限错误流程 |
| 切换医院或医生 | 清理旧智能体内存状态，再读取新作用域 |
| 编辑时切换患者 | 弹窗保持当前智能体编辑；患者选择变化不影响医生级智能体 |

## 12. 验收标准

### 12.1 展示

- 选择患者后，页面公共头部始终展示当前服务智能体；患者列表与患者信息保持独立列和独立区块。
- 智能体名称、医生、职称、科室、状态、简介和知识库数量正确。
- 患者身份与智能体身份视觉上明确分区，不会被误认为同一对象。
- 长名称和长简介不会撑破头部。
- 切换患者不重复闪烁或重新请求同一医生智能体。

### 12.2 编辑

- 点击“编辑智能体”在当前患者工作台打开弹窗。
- 表单字段、校验、保存和提交审核与“我的智能体”页面一致。
- 保存后头部立即显示新值，不刷新整页。
- 关闭弹窗后仍停留在原患者、原滚动位置和原会话抽屉状态。
- 已有患者资料与会话缓存不被清空。
- 不存在第二套重复智能体表单。

### 12.3 异常与可访问性

- 智能体读取或保存失败不阻塞患者工作台。
- 未保存关闭有确认。
- 版本冲突不会静默丢失输入。
- 键盘可完整打开、操作和关闭弹窗。
- 屏幕阅读器能区分患者身份、当前服务智能体和编辑弹窗。

## 13. 非本期范围

- 不在患者工作台创建或分配新的 ClinicalAgentProfile。
- 不改变系统自动选择当前医生智能体的规则。
- 不允许在头部切换多个智能体。
- 不在头部编辑知识库绑定。
- 不在头部编辑场景模型详细参数。
- 不修改患者资料。
- 不改变历史会话绑定的 agent_id。
- 不新增服务端 API 或数据表。
- 不修改 iOS 患者端。

## 14. 实施顺序

1. 将 DoctorAgentForm 的页面外壳与表单主体解耦，保持一套表单业务逻辑。
2. 建立医生级智能体状态，复用现有 API。
3. 在 PatientWorkspacePage 或其上层工作台容器中加入 CurrentAgentHeader，使其位于 PatientListPanel、PatientWorkspaceMain 和患者辅助区的患者业务内容之上；不要把它挂载到 PatientIdentityAndProfile 内部。
4. 实现 AgentEditDialog 并嵌入现有表单。
5. 打通保存/提交后的状态回写。
6. 完成空态、错误态、审核态和版本冲突处理。
7. 验证切换患者、打开会话抽屉、保存智能体时各模块互不干扰。
8. 按本工单验收矩阵回归“我的智能体”独立页面。

## 15. 需求追踪编号

| 编号 | 需求 |
| --- | --- |
| D-001 | 患者工作台公共头部展示当前服务智能体，患者身份在下方患者主区单独展示 |
| D-002 | 智能体信息条展示名称、标识、医生、职称、科室、状态、简介和知识库数量 |
| D-003 | 智能体按当前登录医生现有 doctor_agent 规则取得 |
| D-004 | 点击编辑在患者工作台打开模态弹窗 |
| D-005 | 弹窗复用现有 DoctorAgentForm，不复制表单 |
| D-006 | 保存与提交复用现有三个智能体 API |
| D-007 | 保存成功立即回写头部，不刷新患者工作台 |
| D-008 | 智能体状态按医院与医生隔离，不进入患者级缓存 |
| D-009 | 接口失败局部降级，不阻塞患者工作台 |
| D-010 | 关闭未保存表单必须确认 |
| D-011 | 版本冲突不得静默覆盖医生输入 |
| D-012 | 会话抽屉继续展示会话实际绑定的智能体，不受头部覆盖 |
| D-013 | 患者列表保持原样并作为独立一列，不与患者信息卡合并 |
| D-014 | 当前服务智能体公共头部位于患者列表和患者信息之上 |
