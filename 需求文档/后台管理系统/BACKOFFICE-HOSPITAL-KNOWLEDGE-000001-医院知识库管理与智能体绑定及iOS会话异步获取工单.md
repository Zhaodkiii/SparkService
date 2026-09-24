# BACKOFFICE-HOSPITAL-KNOWLEDGE-000001 医院知识库管理、智能体绑定与 iOS 会话异步获取工单

> 状态：需求已确认，待实施  
> 日期：2026-09-01  
> 目标入口：医院详情 `/hospital-system/{hospital_id}/knowledge`  
> 关联工单：`BACKOFFICE-HOSPITAL-AGENT-000001-医院智能体新建与维护及场景绑定原子创建工单.md`  
> 当前阶段：需求与技术方案；不修改 Python、Vue、Swift、数据库 migration 或部署配置

> **最终产品口径**：已完成一问一答确认，实施必须以[《医院知识库产品需求与落地方案（确认版）》](../../总领文档/医院智能体与医生工作台/医院知识库产品需求与落地方案.md)为准。本文第 3 节及后文保留早期访谈建议和技术探索，用于追溯；其中有关文件上传、审核发布、多层授权范围、患者默认不下载全文等内容，若与确认版冲突，均不再作为实施要求。

## 1. 结论

医院详情页在“智能体”和“服务接入”之间新增一级 Tab“知识库”：

```text
概览｜基础资料｜科室｜职工与医生｜智能体｜知识库｜服务接入｜审计记录
```

知识库的业务所有者是医院，不是录入资料的管理员个人账号，也不是某位医生个人。演示版本仅支持文本录入，无文件上传和审核流程；患者进入对应智能体会话后可按现有同步语义异步获取其关联资料，但不进入个人知识库。

当前 `chat_sync.KnowledgeBase` 强制关联一个 `User`，因此首版建议采用双层所有权：

```text
业务所有者：Hospital
技术承载账号：每家医院一个受控 service User
实际内容容器：复用现有 KnowledgeBase / KnowledgeDocument
医院权限与审核：新增 HospitalKnowledgeBaseProfile 扩展
智能体关联：复用 ClinicalAgentKnowledgeBinding
```

iOS 进入医院智能体对话后不阻塞页面，后台仅同步当前智能体关联知识库的正文、切块、有效向量和删除标记；患者对该资料只读，不能 Push、编辑或删除。

## 2. 当前实现事实

| 能力 | 当前代码事实 | 对本工单的影响 |
| --- | --- | --- |
| KnowledgeBase | `user` 必填，`kind` 支持 personal/shared/system/imported | 当前只能表达技术账号所有，不能直接表达 Hospital 业务所有 |
| KnowledgeDocument | 与 KnowledgeBase 和同一 User 关联，支持 revision、软删除、增量同步 | 内容与同步能力可复用，不新建第二套文档表 |
| 个人同步 API | `/api/v1/ai/knowledge/sync/push/`、`pull/` 均按 `request.user` 隔离 | 不能直接给患者同步医院服务账号的全部内容 |
| iOS KnowledgeSync | 账号级 cursor、Outbox、single-flight、Core Data、本地 Embedding | 适合个人知识库，不应与医院只读内容共用 cursor、Outbox 和编辑能力 |
| 智能体绑定 | 已有 `ClinicalAgentKnowledgeBinding(agent, knowledge_base, usage_scope, status)` | 智能体关联无需复制 KnowledgeBase，只补医院授权与管理 API |
| 医院知识管理页面 | 当前未发现 | 新增医院详情“知识库”Tab、列表、上传、审核、版本和绑定关系页面 |

## 3. 一问一答式需求确认

以下问题必须在开发前由医院信息科、医务处/门诊部、目标科室和产品负责人逐项确认。每题都说明“为什么要问”，避免只收集表面功能偏好。

### Q1：上传后的知识库归谁所有？

为什么要问：现有 `KnowledgeBase` 按 User 隔离。如果归上传管理员个人账号，人员离职、停用或切换账号后会影响知识库管理，也无法证明医院对资料的治理责任。

建议答案：业务上归医院 `Hospital`；技术上由医院专属 service User 承载底层 `KnowledgeBase.user`；上传人只记录为 `created_by`，不成为所有者。

### Q2：“医院公共知识库”是否表示任何患者都能读取全文？

为什么要问：“公共”容易被误解成互联网公开。医院内部指南、培训资料、诊疗规范可能有版权、医疗安全和内部使用限制。

建议答案：不表示公开下载。公共仅表示“医院范围内可复用”；患者默认只能看到 AI 基于资料生成的回答、必要引用标题和就医依据，不能浏览或导出知识库全文。

### Q3：知识库需要哪些可见范围？

为什么要问：医院级、科室级和智能体专属资料的审核责任与误用风险不同。全院资料如果默认绑定所有智能体，容易出现跨科室错误引用。

建议答案：支持三层：

- `hospital`：全院智能体可申请绑定。
- `department`：仅指定一个或多个科室可绑定。
- `restricted`：仅明确选择的智能体可绑定。

### Q4：谁可以上传，谁可以审核发布？

为什么要问：上传文件不等于内容可以进入 AI 生产检索。若上传者可直接发布，无法落实医疗内容审核和责任追踪。

建议答案：医院知识管理员可上传形成草稿；科室内容审核人确认医学内容；医院信息科确认来源、权限与脱敏；审核通过后才能变为 `published` 并允许智能体绑定。

### Q5：允许上传哪些类型的资料？

为什么要问：PDF、Word、网页、扫描件和原始病历的解析质量、授权与脱敏风险不同，不能统一当作纯文本处理。

建议答案：首版支持医院自有且已授权的 PDF、Word、Markdown、TXT；扫描件进入 OCR 后必须人工复核。原始病历、患者列表、处方记录和含身份信息的附件默认禁止上传。

### Q6：资料的来源、版本和有效期如何记录？

为什么要问：医疗指南会更新。没有来源和失效时间，AI 可能持续引用已经废止的流程或旧指南。

建议答案：每份文档必须记录来源机构、来源类型、原始文件、版本号、发布日期、适用科室、生效时间、失效时间、上传人和审核人；到期自动进入待复审，不直接物理删除。

### Q7：一份知识库可以绑定多少智能体？

为什么要问：如果一库一智能体，会大量复制文档；如果默认绑定全部智能体，会扩大错误使用范围。

建议答案：一份知识库可以绑定多个智能体，一个智能体也可绑定多个知识库；通过现有 `ClinicalAgentKnowledgeBinding` 建立多对多引用，不复制文档。

### Q8：创建智能体时能否直接选择知识库？

为什么要问：智能体创建是最自然的配置入口，但如果列表包含草稿、其他医院或无权使用的知识库，会造成越权和发布失败。

建议答案：可以。智能体表单只展示当前医院、已发布且与所选科室兼容的知识库；保存时同时创建绑定。后续可在知识库详情反向查看和维护关联智能体。

### Q9：知识库更新后，已绑定智能体是否立即使用新内容？

为什么要问：医疗资料更新不应在未审核时自动影响线上回答，也需要避免对话中途检索口径突然变化。

建议答案：采用发布版本。编辑产生新草稿版本，审核发布后生成新 revision；新会话使用最新发布版本，进行中的会话按创建时 manifest revision 固定，除非发生安全紧急下架。

### Q10：知识库停用时，历史会话和引用怎么办？

为什么要问：物理删除会破坏历史解释性；继续检索又可能引用不安全内容。

建议答案：停用后禁止新检索和新绑定，历史消息保留引用快照（标题、版本、来源、引用片段 hash），不保留患者可下载的原始文件直链。

### Q11：iOS 进入对话后，为什么需要下载知识库？

为什么要问：如果目标只是让服务端 AI 回答，下载完整知识库没有必要，反而增加隐私泄漏、存储、流量和版本一致性风险。

建议答案：默认不下载正文。iOS 只异步获取 manifest 与引用元数据，用于显示“该智能体使用哪些医院资料、当前版本和来源”。只有明确的离线咨询场景才下载审核后的只读快照。

### Q12：哪些内容允许下发到患者设备？

为什么要问：进入手机缓存后，医院很难彻底控制复制、备份、截屏和越狱设备读取。

建议答案：每个知识库必须配置 `server_only / citation_only / offline_snapshot`：

- `server_only`：仅服务端 RAG，不下发正文。
- `citation_only`：下发标题、版本、来源和 AI 实际引用的短片段。
- `offline_snapshot`：只下发医院批准的患者教育子集，不包含内部规范、原始病历或受版权限制全文。

### Q13：进入对话是否等待知识库下载完成？

为什么要问：将下载作为页面门禁会拖慢首屏、弱网不可用，也会把“资料同步失败”错误变成“无法咨询”。

建议答案：不等待。对话页立即展示；后台异步 single-flight 获取 manifest。服务端 RAG 可用时正常咨询；离线快照失败只影响离线能力，不影响在线对话。

### Q14：患者切换家庭成员、账号或退出后如何处理缓存？

为什么要问：当前 iOS 同时存在账号和就诊成员两个范围。只按设备缓存会造成账号 A 或成员 A 的对话上下文被其他人复用。

建议答案：缓存键至少包含 `account_id + member_id + hospital_id + agent_id + knowledge_base_id + revision`；切换账号立即取消旧任务并清理密钥，成员切换不混用对话 manifest；授权撤回、会话结束或 TTL 到期按策略清理。

### Q15：医生能否把患者病历上传为医院知识？

为什么要问：脱敏不等于可以二次训练或共享。病例可能仍可被重新识别，也可能超出患者授权用途。

建议答案：首版禁止。若后续需要病例知识，必须走独立的数据治理流程，形成经审核的结构化匿名病例摘要，并记录合法依据、脱敏标准、用途和撤回机制。

## 4. 后台信息架构与页面原型

### 4.1 知识库列表

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ 知识库管理                                                [+ 新建知识库]    │
│ 管理医院共享资料、科室授权、智能体绑定和发布版本                          │
├──────────────────────────────────────────────────────────────────────────────┤
│ [搜索名称/文档] [范围：全部⌄] [科室⌄] [状态⌄] [查询] [重置]              │
├──────────────────────────────────────────────────────────────────────────────┤
│ 名称              范围       科室       文档数  关联智能体  版本  状态  操作│
│ 心内科就医指南    科室级     心内科       18        3       v7   已发布 详情│
│ 医院就诊须知      全院级     全部          6       12       v3   已发布 详情│
│ 皮肤科病例资料    受限       皮肤科        2        0       v1   待审核 审核│
├──────────────────────────────────────────────────────────────────────────────┤
│ 共 3 条                                                   < 1 >              │
└──────────────────────────────────────────────────────────────────────────────┘
```

页面状态：

| 状态 | 表现 |
| --- | --- |
| loading | 筛选和表格骨架，不显示假数据 |
| empty | “尚未创建医院知识库”，有权限时显示新建按钮 |
| filtered_empty | 保留筛选条件并提供清除筛选 |
| error | 保留上次成功结果，显示 request ID 和重试 |
| unauthorized | 返回医院概览，不暴露知识库名称和文档数量 |

### 4.2 新建知识库

```text
┌──────────────────────────────────────────────────────────────────────┐
│ 新建医院知识库                                                  [×] │
├──────────────────────────────────────────────────────────────────────┤
│ 名称 *                [________________________________________]      │
│ 说明                  [________________________________________]      │
│ 使用范围 *            (●) 全院  ( ) 科室  ( ) 指定智能体            │
│ 允许科室              [选择科室⌄]                                   │
│ 客户端分发策略 *      (●) 仅服务端  ( ) 仅引用  ( ) 离线快照         │
│ 内容负责人 *          [选择职工⌄]                                   │
│ 复审周期              [180 天⌄]                                     │
├──────────────────────────────────────────────────────────────────────┤
│                                          [取消] [保存草稿]           │
└──────────────────────────────────────────────────────────────────────┘
```

保存只创建草稿容器，不自动发布，也不默认绑定所有智能体。

### 4.3 知识库详情

```text
心内科就医指南  [已发布]  v7
[概览] [文档] [科室授权] [关联智能体] [版本与审核] [访问审计]

文档 Tab
[上传文件] [新建文本] [批量提交审核]

文档名称                来源       当前版本   解析状态   审核状态  操作
胸痛就医流程.pdf        医院文件      3       已完成     已发布    预览
心衰患者教育.docx       科室上传      1       解析失败   草稿      重试
```

上传流程必须分为：上传登记 → 病毒/类型/大小校验 → 文本提取/OCR → 脱敏检测 → 人工预览 → 医学审核 → 发布。`上传成功` 不能等同于 `可被 AI 检索`。

### 4.4 智能体创建/维护中的知识库选择

```text
知识库关联（可多选）
[搜索当前医院已发布知识库……]

☑ 医院就诊须知       全院级   v3   仅服务端
☑ 心内科就医指南     心内科   v7   仅引用
☐ 心内科患者教育     心内科   v2   允许离线快照

已选择 2 个知识库
检索顺序：[医院就诊须知 ↑↓] [心内科就医指南 ↑↓]
```

表单选项由后端按当前 hospital、doctor、department、publication status 和权限过滤。前端不能传入其他医院的 KnowledgeBase ID，也不能修改知识库分发策略。

## 5. 服务端数据设计

### 5.1 复用模型

- `KnowledgeBase`：继续作为内容容器；`user` 指向医院受控 service User。
- `KnowledgeDocument`：继续承载正文、revision、来源文件、软删除和增量更新时间。
- `ClinicalAgentKnowledgeBinding`：继续承载智能体与知识库的引用、顺序、状态和批准人。

### 5.2 目标新增医院扩展实体

建议新增 `HospitalKnowledgeBaseProfile`，不复制文档正文：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | 医院知识库业务 ID |
| `hospital` | FK Hospital, PROTECT | 业务所有者 |
| `knowledge_base` | OneToOne KnowledgeBase, PROTECT | 底层容器 |
| `visibility_scope` | hospital/department/restricted | 允许绑定范围 |
| `distribution_policy` | server_only/citation_only/offline_snapshot | 患者端下发策略 |
| `status` | draft/processing/review/published/disabled | 治理状态 |
| `content_owner_staff` | FK HospitalStaffMembership | 内容负责人 |
| `published_revision` | bigint | 当前生产版本 |
| `review_due_at` | datetime | 下次复审时间 |
| `created_by/approved_by` | FK User | 上传与审核责任留痕 |
| `version` | bigint | 后台乐观锁 |
| `created_at/updated_at` | datetime | 审计时间 |

建议新增 `HospitalKnowledgeBaseDepartmentGrant(profile, department)`，表达一个知识库可授权多个科室。智能体专属范围继续由 `ClinicalAgentKnowledgeBinding` 表达，不在 Profile 内保存 JSON ID 列表。

“医院服务账号”不是可登录的普通医生账号：

- 每家医院一个稳定账号，用于现有 `KnowledgeBase.user` 和 `KnowledgeDocument.user` 外键。
- 不授予后台登录、医生工作台或患者身份。
- 禁止前端接收其 Token；所有操作由医院知识 Service 在服务端代为执行。
- 医院停用时不级联删除该账号或内容，先冻结知识库和访问授权。

## 6. 服务端接口契约

### 6.1 平台后台

```text
GET  /api/admin/v1/hospital-care/hospitals/{hospital_id}/knowledge-bases/
POST /api/admin/v1/hospital-care/hospitals/{hospital_id}/knowledge-bases/
GET  /api/admin/v1/hospital-care/knowledge-bases/{profile_id}/
PATCH /api/admin/v1/hospital-care/knowledge-bases/{profile_id}/
POST /api/admin/v1/hospital-care/knowledge-bases/{profile_id}/documents/upload-ticket/
POST /api/admin/v1/hospital-care/knowledge-bases/{profile_id}/documents/
POST /api/admin/v1/hospital-care/knowledge-bases/{profile_id}/submit/
POST /api/admin/v1/hospital-care/knowledge-bases/{profile_id}/review/
POST /api/admin/v1/hospital-care/knowledge-bases/{profile_id}/disable/
PUT  /api/admin/v1/hospital-care/knowledge-bases/{profile_id}/agent-bindings/
GET  /api/admin/v1/hospital-care/knowledge-bases/{profile_id}/audit-logs/
```

所有写操作携带 `Idempotency-Key`；更新、审核、停用携带 `version`。View 只做认证与 Serializer 校验，写入统一进入 `HospitalKnowledgeService`，并复用现有知识文档 Service，不直接绕过 owner 过滤修改数据库。

### 6.2 智能体表单选项

此前智能体工单的 `agent-form-options` 响应增加：

```json
{
  "knowledge_bases": [
    {
      "profile_id": "uuid",
      "knowledge_base_id": "uuid",
      "name": "心内科就医指南",
      "visibility_scope": "department",
      "distribution_policy": "citation_only",
      "published_revision": 7,
      "allowed_department_ids": ["uuid"]
    }
  ]
}
```

服务端只返回与当前医院、所选科室及操作者权限匹配的 `published` 条目。

### 6.3 患者会话知识 manifest

创建医院会话或读取会话 context 时返回知识 manifest 摘要：

```json
{
  "knowledge_manifest": {
    "manifest_revision": 12,
    "generated_at": "2026-09-01T12:00:00Z",
    "bases": [
      {
        "knowledge_base_id": "uuid",
        "name": "心内科就医指南",
        "published_revision": 7,
        "distribution_policy": "citation_only",
        "document_count": 18,
        "offline_package": null
      }
    ]
  }
}
```

如需独立刷新：

```text
GET /api/v1/hospital-care/conversations/{thread_id}/knowledge-manifest/
```

权限必须同时验证：当前 User 拥有 Thread、当前 member_id 可访问、会话绑定对应发布智能体、知识库仍授权给该智能体。不得直接复用个人 `/api/v1/ai/knowledge/sync/pull/`，因为该接口按患者账号同步个人知识，而医院知识底层属于医院 service User。

## 7. iOS 进入对话后的异步设计

### 7.1 默认链路

```text
进入医院对话
  ├─ 立即展示 Thread / Message / Composer
  └─ 后台 Task：读取 conversation context 中的 knowledge_manifest
       ├─ manifest revision 命中本地缓存 → 不下载
       ├─ server_only → 仅缓存名称、版本、来源说明
       ├─ citation_only → 仅在 AI 实际引用时拉取引用元数据
       └─ offline_snapshot → 满足网络/授权/空间条件后下载只读加密包
```

下载失败不阻断在线聊天。页面只显示非阻断状态，例如“医院资料正在更新”“离线资料暂不可用”；不能把知识下载失败转成“智能体不可使用”。

### 7.2 不复用个人知识库本地表

当前 iOS `KnowledgeSyncEngine` 是账号级可编辑同步，带 Push Outbox、个人 cursor 和本地 Embedding。医院知识快照必须另建只读存储边界，例如：

```text
Features/HospitalCare/Knowledge/
├── Domain/HospitalKnowledgeManifest.swift
├── Application/RefreshHospitalKnowledgeManifestUseCase.swift
├── Infrastructure/HospitalKnowledgeManifestAPI.swift
├── Infrastructure/HospitalKnowledgeSnapshotStore.swift
└── Infrastructure/HospitalKnowledgeDownloadCoordinator.swift
```

这是目标目录设计，不是当前已实现代码。它不得写入个人 `KnowledgeDocumentEntity`，不得产生个人知识 Push mutation，也不得让患者编辑后回传医院知识库。

### 7.3 并发、缓存与取消

- single-flight key：`accountID/memberID/threadID/manifestRevision`。
- 同一智能体多个会话可复用相同 `hospitalID/agentID/baseID/revision` 的只读包，但授权判断仍按当前会话重新完成。
- 进入新会话时取消不再需要的低优先级下载；已完成下载按 LRU/TTL 管理。
- 账号切换立即递增 generation，旧任务迟到结果不得写入新账号缓存。
- member 切换不改绑历史 Thread；新 member 进入时重新取 manifest。
- 仅 Wi-Fi 下载大包的开关属于产品策略；蜂窝网络超过阈值前需提示大小。

### 7.4 安全要求

- 文件存放在 App 私有目录，使用按账号派生的本地加密密钥；密钥不进入 UserDefaults、日志或数据库明文字段。
- 下载使用短时授权 URL 或受鉴权流式接口；URL 不写普通日志和分享内容。
- 包含 `package_id/schema_version/base_id/revision/sha256/expires_at`，落盘前校验哈希和签名。
- 不备份到 iCloud；截屏和越狱设备无法完全防止泄露，因此离线包只能包含允许患者持有的资料。
- 授权撤回、医院紧急下架、账号退出、TTL 到期时清理包和索引。
- 医院知识检索默认在服务端完成；不要把医院完整向量库、Embedding Key 或 Provider Key 下发到 iOS。

## 8. AI 运行时使用规则

服务器创建 Chat Run 时，应通过：

```text
ChatThread.hospital_binding
  -> ClinicalAgentProfile
  -> active ClinicalAgentKnowledgeBinding
  -> published HospitalKnowledgeBaseProfile
  -> 当前 published_revision 的 KnowledgeDocument 集合
```

检索结果必须携带知识库 ID、文档 ID、发布版本、片段 hash 和来源标题，供消息引用卡片展示及审计。知识库临时不可用时，AI 应明确降级：不声称“依据医院知识库”，并记录内部可观测错误；不得静默改用其他医院或医生个人知识库。

多个知识库同时绑定时，`sort_order` 只决定检索优先级，不代表低顺序库被完全排除。必须设置总 top-k、单库上限、去重和冲突规则；医学资料冲突时优先最新已发布且适用范围更具体的版本，并在无法消解时转人工审核。

## 9. 权限、审计和状态机

建议新增权限：

```text
menu:hospital_care:knowledge
api:hospital_care:knowledge:list/read/create/update
api:hospital_care:knowledge:document_upload
api:hospital_care:knowledge:submit/review/disable
api:hospital_care:knowledge:agent_bindings
api:hospital_care:knowledge:audit
button:hospital_care:knowledge:create/upload/review/disable
```

状态机：

```text
draft → processing → review → published → review（新版本）
                                  └──────→ disabled
processing_failed → processing（重试）
```

审计动作至少包括：创建库、修改范围、上传文件、解析完成/失败、提交审核、发布版本、停用、绑定/解绑智能体、生成离线包、患者 manifest 获取和离线包下载。审计不记录正文、原始文件 URL、患者身份全文、Token、密钥或完整检索上下文。

## 10. 错误码

| 业务码 | HTTP | 含义 |
| --- | --- | --- |
| `HOSPITAL_KNOWLEDGE_NOT_FOUND` | 404 | 当前医院范围内不存在 |
| `HOSPITAL_KNOWLEDGE_SCOPE_FORBIDDEN` | 403 | 科室、智能体或管理员范围不允许 |
| `HOSPITAL_KNOWLEDGE_VERSION_CONFLICT` | 409 | 后台并发修改冲突 |
| `HOSPITAL_KNOWLEDGE_NOT_PUBLISHED` | 409 | 草稿/处理中内容不可绑定或检索 |
| `HOSPITAL_KNOWLEDGE_DOCUMENT_REJECTED` | 422 | 文件类型、脱敏或合规检查失败 |
| `HOSPITAL_KNOWLEDGE_PROCESSING` | 409 | 解析未完成 |
| `HOSPITAL_KNOWLEDGE_BINDING_CONFLICT` | 409 | 重复绑定或范围不兼容 |
| `HOSPITAL_KNOWLEDGE_OFFLINE_FORBIDDEN` | 403 | 不允许客户端下载正文 |
| `HOSPITAL_KNOWLEDGE_PACKAGE_EXPIRED` | 410 | 离线包授权或版本已过期 |

继续使用项目统一 `{ code, msg, data }` 与 `X-Request-ID`。iOS 不解析英文异常文本，Web 表单按 `details.field` 定位字段。

## 11. 实施拆分

| 阶段 | 服务端 / 后台 | iOS | 出口条件 |
| --- | --- | --- | --- |
| K0 | 医院确认归属、范围、审核、分发政策 | 不改 | 问答项有负责人和结论 |
| K1 | Profile/Grant 模型、service User、迁移、权限、审计 | 不改 | 所有知识库具备医院业务归属 |
| K2 | 知识库 Tab、容器/文档上传、解析、审核和版本页面 | 不改 | 已发布版本可追溯，原文无越权 |
| K3 | 智能体创建/维护可选知识库，绑定 API | 不改 | 跨医院/跨科室绑定测试通过 |
| K4 | AI Runtime 按医院智能体绑定做服务端 RAG | 只展示引用 | 对话确实使用绑定版本并可审计 |
| K5 | conversation manifest | 异步 manifest、引用展示 | 不阻断聊天，账号/成员隔离通过 |
| K6 | 可选离线快照服务 | 加密下载、只读缓存、撤回清理 | 仅批准资料可落盘，安全验收通过 |

## 12. 验收标准

1. 医院详情在智能体后增加“知识库”Tab，URL 为 `/hospital-system/{hospital_id}/knowledge`。
2. 新建知识库时业务归属为当前 Hospital，底层 KnowledgeBase 由该医院受控 service User 承载，不属于上传管理员个人。
3. 其他医院、未授权科室和患者账号不能枚举知识库名称、文档数、正文或下载地址。
4. 上传、解析、审核、发布分离；未发布文档不能被智能体检索。
5. 智能体创建和维护只能选择当前医院、当前科室兼容的已发布知识库，可多选并排序。
6. 知识库更新采用发布 revision；进行中会话使用冻结 manifest，紧急下架除外。
7. iOS 进入对话立即可聊天，manifest 获取和可选下载均在后台异步执行。
8. 默认 `server_only` 不向 iOS 下载正文；个人知识库同步表、cursor 和 Outbox 不混入医院内容。
9. 离线包校验、加密、账号切换取消、授权撤回、TTL 清理和弱网恢复都有测试。
10. AI 回答引用可追溯到医院知识库、文档和发布版本；知识不可用时不伪造“院内资料依据”。

## 13. 目标实施文件

| 位置 | 目标变更 |
| --- | --- |
| `hospital_care/models/knowledge.py` | HospitalKnowledgeBaseProfile、DepartmentGrant |
| `hospital_care/services/hospital_knowledge_service.py` | 所有权、上传、审核、版本、绑定、停用 |
| `hospital_care/selectors/hospital_knowledge_catalog.py` | 后台列表、智能体可选项、患者 manifest |
| `hospital_care/api/backoffice/` | 医院知识管理 API |
| `hospital_care/api/patient/` | 会话 knowledge manifest API |
| `hospital_care/permissions.py` | 医院知识管理与患者会话读取权限 |
| `hospital_care/exceptions.py` | 稳定业务错误码 |
| `backoffice/rbac.py` | 菜单、按钮与 API 权限种子 |
| `backoffice-web/src/router/routes.ts` | `/hospital-system/:hospitalId/knowledge` |
| `backoffice-web/src/api/modules/hospitalCare.ts` | 知识库 DTO 与 API |
| `backoffice-web/src/views/hospital-care/` | Knowledge 页面、上传/审核 Drawer |
| `chat_sync/ai_services/context/` | 按医院智能体绑定解析服务端 RAG |
| iOS `Features/HospitalCare/Knowledge/` | manifest 和可选离线只读快照，后续阶段实现 |
| `hospital_care/tests/` | 所有权、权限、审核、绑定、manifest、下架测试 |

## 14. 明确不做

- 不把医院知识库复制成每个医生或患者的个人 KnowledgeBase。
- 不允许患者端向医院知识库 Push、编辑或解决冲突。
- 不默认下载医院知识全文、内部诊疗规范、原始病历或向量索引。
- 不把“文件上传成功”显示为“AI 已可使用”。
- 不使用管理员个人 User 作为长期医院知识所有者。
- 不因为知识库暂不可用而阻断整个对话页面。
