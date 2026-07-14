# MEDICAL-ARCHIVE-000001 医疗档案归档功能详设工单

## 1. 工单摘要

| 项目 | 内容 |
|---|---|
| 工单名称 | 医疗档案归档功能 |
| 需求范围 | SparkClient、SparkService |
| 业务对象 | 病历、体检报告、检查报告、处方、服用计划、药品 |
| 服务端模型 | `MedicalCase`、`HealthExamReport`、`ExaminationReport`、`Prescription`、`MedicationPlan`、`MedicineBox` |
| 当前状态 | 待实现 |
| 优先级 | P1 |

## 2. 背景

当前医疗档案只有正常列表和软删除能力。用户对历史资料、已停用药品、已完成服用计划、过期处方等数据，既不希望继续出现在日常列表中，也不希望删除后失去历史追溯能力。

因此需要新增“归档”能力：

1. 归档数据仍然保留在业务表中。
2. 归档数据默认不出现在正常列表、首页汇总、医疗档案汇总中。
3. 用户可以进入归档记录列表查看历史数据。
4. 归档动作与删除动作分离，归档后仍允许查看详情、取消归档或删除。

## 3. 目标

1. 客户端在目标详情页右上角菜单新增“归档”操作。
2. 客户端归档前必须二次确认。
3. 服务端统一支持目标模型的归档状态字段。
4. 正常列表默认过滤归档数据。
5. 归档列表通过显式查询参数返回归档数据。
6. 客户端接口模型、列表页、详情页、缓存刷新逻辑适配归档字段。
7. 保持现有软删除、成员权限、附件、分享、用药提醒等能力不被破坏。

## 4. 非目标

1. 本工单不做物理删除。
2. 本工单不做归档原因必填。
3. 本工单不新增独立归档表。
4. 本工单不做批量归档，除非后续产品单独提出。
5. 本工单不改变现有业务对象的创建和编辑主流程。

## 5. 归档语义

| 状态 | 条件 | 展示位置 | 可恢复 | 可删除 |
|---|---|---|---|---|
| 正常 | `is_deleted=false` 且 `is_archived=false` | 正常列表、首页、医疗档案汇总 | 不需要 | 是 |
| 已归档 | `is_deleted=false` 且 `is_archived=true` | 归档记录列表、详情直达 | 是 | 是 |
| 已删除 | `is_deleted=true` | 不在普通业务列表展示 | 视现有删除策略决定 | 不适用 |

归档不是删除。归档后数据仍属于原成员、原用户、原业务类型，附件关系、关联关系、分享关系原则上保留。

## 6. 服务端数据模型设计

### 6.1 基础模型字段

在 `SparkService/medical/models.py` 的 `MedicalBaseModel` 增加统一归档字段：

```text
is_archived      boolean      default false, db_index=True, db_comment="是否归档"
archived_at      datetime     null=True, blank=True, db_comment="归档时间"
```

推荐放到 `MedicalBaseModel`，原因是医疗业务表已经统一继承该基类，未来成员资料、报告、用药计划、药箱等对象都可能需要归档能力。统一放基类可以减少后续模型分叉。

### 6.2 字段更新规则

| 动作 | `is_archived` | `archived_at` | `updated_at` |
|---|---:|---|---|
| 归档 | `true` | 当前服务端时间 | 更新 |
| 取消归档 | `false` | `null` | 更新 |
| 删除 | 不强制修改 | 保持原值 | 更新 |
| 新建 | `false` | `null` | 自动生成 |

### 6.3 建议模型方法

在 `MedicalBaseModel` 增加统一方法：

```text
archive()
unarchive()
```

方法职责：

1. 幂等处理，重复归档不重复刷新 `archived_at`。
2. 取消归档时清空 `archived_at`。
3. 保存字段包含 `is_archived`、`archived_at`、`updated_at`。

### 6.4 数据库迁移

新增迁移需要覆盖所有继承 `MedicalBaseModel` 的具体表。目标业务对象必须包含：

1. `medical_medical_case`
2. `medical_health_exam_report`
3. `medical_examination_report`
4. `medical_prescription`
5. `medical_medication_plan`
6. `medical_medicine_box`

如果迁移自动覆盖了更多医疗表，属于可接受结果，但接口层只开放本工单目标对象的归档入口。

### 6.5 索引建议

基础字段 `is_archived` 需要单列索引。目标表还建议补充组合索引，优先覆盖常用列表查询：

```text
MedicalCase:        (user, member, is_deleted, is_archived)
HealthExamReport:   (user, member, is_deleted, is_archived)
ExaminationReport:  (user, member, is_deleted, is_archived)
Prescription:       (user, member, is_deleted, is_archived)
MedicationPlan:     (user, member, is_deleted, is_archived)
MedicineBox:        (user, member, is_deleted, is_archived)
MedicineBox:        (user, member, medicine_type, is_deleted, is_archived)
```

如果迁移风险较高，第一期可以只加字段索引，组合索引跟随慢查询结果补充。

## 7. 服务端接口设计

### 7.1 列表查询参数

所有目标资源列表支持统一查询参数：

```text
archived=false   默认值，返回正常记录
archived=true    返回归档记录
archived=all     返回正常 + 归档记录，仅内部调试或明确业务需要时使用
```

不携带 `archived` 时必须等价于：

```text
archived=false
```

正常列表过滤条件：

```text
is_deleted=false AND is_archived=false
```

归档列表过滤条件：

```text
is_deleted=false AND is_archived=true
```

### 7.2 目标列表接口

| 业务 | 接口资源 | 正常列表 | 归档列表 |
|---|---|---|---|
| 病历 | `/medical/cases/` | 不带 `archived` | `?archived=true` |
| 体检 | `/medical/health-exam-reports/` | 不带 `archived` | `?archived=true` |
| 检查报告 | `/medical/examination-reports/` | 不带 `archived` | `?archived=true` |
| 处方 | `/medical/prescriptions/` | 不带 `archived` | `?archived=true` |
| 服用计划 | `/medical/medication-plans/` | 不带 `archived` | `?archived=true` |
| 药品 | `/medical/medicine-boxes/` | 不带 `archived` | `?archived=true` |

现有 `member_id`、`status`、`medicine_type`、`expire_before`、`low_stock` 等筛选参数继续生效，和 `archived` 叠加过滤。

### 7.3 归档状态提交

推荐复用现有资源详情 `PATCH`：

```http
PATCH /medical/{resource}/{id}/
Content-Type: application/json

{
  "is_archived": true
}
```

取消归档：

```http
PATCH /medical/{resource}/{id}/
Content-Type: application/json

{
  "is_archived": false
}
```

服务端需要在更新时统一处理：

1. `is_archived=true` 时设置 `archived_at=timezone.now()`。
2. `is_archived=false` 时设置 `archived_at=null`。
3. 校验用户对所属成员具有编辑权限。
4. 响应返回更新后的完整对象。

如果后续希望把语义做得更强，也可以增加自定义 action：

```text
POST /medical/{resource}/{id}/archive/
POST /medical/{resource}/{id}/unarchive/
```

第一期建议使用 `PATCH`，客户端适配成本最低，也和现有更新接口一致。

### 7.4 序列化响应字段

目标资源列表和详情响应必须新增：

```text
is_archived
archived_at
```

这些字段对客户端是必需字段，用于：

1. 详情页菜单展示“归档”或“取消归档”。
2. 本地模型判断是否需要从正常列表移除。
3. 归档列表复用现有 cell/card。
4. ETag 和缓存刷新判断。

### 7.5 基础查询层改造

建议在 `WrappedModelViewSet.get_queryset()` 增加统一归档过滤，避免每个 ViewSet 手写遗漏。

过滤规则：

```text
archived=true  -> filter(is_archived=True)
archived=all   -> 不按 is_archived 过滤
其他/空值       -> filter(is_archived=False)
```

`MedExamDetail` 不是本工单目标归档对象，原则上不需要支持归档查询参数。

### 7.6 汇总接口过滤

以下接口中目标资源也必须默认过滤 `is_archived=false`：

1. 成员医疗数据汇总接口：`MemberBindingViewSet.get`
2. 医疗引导首页状态接口：`MemberGuidanceStateAPI`
3. 家庭药箱汇总接口：`FamilyMedicineCabinetSummaryAPI`
4. 用药首页、今日用药、提醒相关查询中依赖 `MedicationPlan` / `MedicineBox` 的逻辑

特别规则：

1. 归档药品不应出现在家庭药箱正常列表。
2. 归档服用计划不应进入日常服药计划列表。
3. 归档服用计划不应继续生成新的提醒或健康通知。
4. 历史服药记录 `MedicationRecord` 不因为计划归档而删除。

### 7.7 详情查询规则

详情接口允许读取已归档对象：

```text
GET /medical/{resource}/{id}/
```

原因：

1. 归档列表点击后需要进入详情。
2. 分享、通知、历史跳转可能持有对象 id。

但软删除对象仍按现有规则不可读。

### 7.8 分享与关联关系

归档不应破坏关联关系：

1. 病历归档时，不自动归档其处方、检查报告、服用计划。
2. 处方归档时，不自动归档其服用计划。
3. 药品归档时，不自动归档其服用计划。
4. 服用计划归档时，不删除历史服药记录。

分享读取建议保持可访问，但列表入口不主动展示归档资源。若产品后续要求“归档后分享失效”，需要单独增加分享状态规则，本工单不处理。

### 7.9 服务端归档过滤实现细节

建议增加一个统一解析函数，避免不同 ViewSet 对 `archived` 参数理解不一致：

```text
parse_archived_param(request) -> "active" | "archived" | "all"
```

参数规则：

| 请求值 | 语义 |
|---|---|
| 空、`false`、`0`、`no` | 正常记录 |
| `true`、`1`、`yes` | 已归档记录 |
| `all` | 正常 + 已归档 |
| 其他值 | 返回 `400 invalid_archived_param` |

建议 `WrappedModelViewSet.get_queryset()` 中的处理顺序：

1. 先过滤 `is_deleted=false`。
2. 再做成员权限过滤或 `user=request.user` 过滤。
3. 再根据 `archived` 参数过滤归档状态。
4. 最后由各 ViewSet 追加 `member_id`、`status`、`medicine_type` 等业务筛选。

这样可以保证归档过滤不会绕过成员权限，也不会让软删除数据因为 `archived=all` 被查出来。

### 7.10 服务端更新实现细节

归档状态更新建议在基础更新流程中统一处理，不建议每个 Serializer 自己写一遍。

推荐规则：

1. 请求体包含 `is_archived` 时，视为归档状态变更请求。
2. `is_archived=true` 且实例当前未归档：设置 `archived_at=timezone.now()`。
3. `is_archived=true` 且实例已归档：保持原 `archived_at` 不变，保证幂等。
4. `is_archived=false`：设置 `archived_at=null`。
5. 请求体不包含 `is_archived`：不得改动 `is_archived/archived_at`。

建议在 `perform_update()` 或模型方法中处理，而不是依赖客户端提交 `archived_at`。

### 7.11 服务端 Serializer 字段策略

目标资源 Serializer 的 `fields` 必须增加：

```text
is_archived
archived_at
```

推荐 `read_only_fields`：

```text
archived_at
```

`is_archived` 可以写入，`archived_at` 只读。这样客户端可以通过 PATCH 切换归档状态，但无法伪造归档时间。

对于工作流保存接口：

1. OCR/AI 保存新资源时不允许传入归档状态。
2. 工作流新建的资源默认 `is_archived=false`。
3. 工作流更新已有资源时，如果 payload 未包含 `is_archived`，不得重置原归档状态。

### 7.12 服务端 ETag 与缓存细节

现有列表 ETag 基于 `path`、`query`、`user_id`、`records(id, updated_at)` 构建。归档改造后需要保证：

1. `archived=false` 和 `archived=true` 的列表 ETag 互相独立，因为 `query` 不同。
2. 归档和取消归档必须刷新 `updated_at`，否则客户端可能继续命中旧 ETag。
3. `archived=all` 也必须纳入 query 指纹。
4. 汇总接口 `/members/{id}/complete-data/` 的 ETag 构建需要包含归档状态变化后的目标资源集合。

归档成功后，正常列表会少一条记录，归档列表会多一条记录。两边的 ETag 都必须随 `updated_at` 或 records 集合变化而变化。

### 7.13 服务端用药提醒联动

服用计划归档属于“计划不再参与未来执行”的业务动作。服务端需要统一处理：

1. `MedicationPlan.is_archived=true` 后，不再出现在提醒开启计划接口。
2. 今日用药、未来窗口用药记录生成逻辑应排除归档计划。
3. 已经生成的历史 `MedicationRecord` 保留。
4. 如果已有未来 `MedicationRecord` 预生成机制，归档时不强制删除历史记录，但未来待执行记录是否标记失效需要产品确认。

本工单第一期最低要求：所有查询和通知聚合接口排除归档服用计划，避免归档后继续提醒。

### 7.14 服务端审计与日志建议

归档是用户主动整理资料的行为，建议记录普通业务日志：

```text
actor_user_id
resource_kind
resource_id
member_id
from_is_archived
to_is_archived
archived_at
request_id
```

如果现有 `ModelChangeLog` 已用于医疗数据变更，可把归档/取消归档纳入变更类型；如果没有统一落库要求，至少保留应用日志，便于排查“记录为什么从列表消失”。

## 8. 客户端设计

### 8.1 数据模型适配

客户端目标模型新增字段：

```swift
let isArchived: Bool
let archivedAt: Date?
```

JSON 映射：

```text
is_archived -> isArchived
archived_at -> archivedAt
```

兼容策略：

1. 旧服务端没有返回 `is_archived` 时，客户端默认 `false`。
2. 旧服务端没有返回 `archived_at` 时，客户端默认 `nil`。
3. 客户端提交归档时只提交 `is_archived`，不提交 `archived_at`。

### 8.2 详情页入口

以下详情页右上角菜单新增归档状态操作：

1. 病历详情
2. 体检报告详情
3. 检查报告详情
4. 处方详情
5. 服用计划详情
6. 药品详情

菜单逻辑：

| 当前状态 | 菜单项 |
|---|---|
| 正常 | 归档 |
| 已归档 | 取消归档 |

详情页按钮必须由当前记录的 `is_archived` 状态驱动：

1. 正常记录进入详情页时，菜单显示“归档”。
2. 已归档记录进入详情页时，菜单显示“取消归档”，不得继续显示“归档”。
3. 从归档记录列表进入详情页时，也必须按已归档状态显示“取消归档”。

点击“归档”后弹出二次确认：

```text
标题：归档此记录？
说明：归档后不会出现在正常列表中，你仍可在归档记录中查看和恢复。
按钮：取消 / 归档
```

点击“取消归档”后弹出二次确认：

```text
标题：恢复此记录？
说明：恢复后会重新出现在正常列表中。
按钮：取消 / 恢复
```

“取消归档”和“归档”一样必须二次确认，用户确认前不得提交接口请求或提前修改本地列表状态。

确认后调用对应资源的 `PATCH` 接口更新服务器状态。

### 8.3 归档成功后的客户端状态

从正常详情页归档成功后：

1. Toast：`已归档`。
2. 当前详情页可以保留，但菜单切换为“取消归档”。
3. 返回正常列表时，该记录应从列表中移除。
4. 刷新成员医疗汇总缓存或对应列表缓存。

从归档详情页取消归档成功后：

1. Toast：`已恢复`。
2. 当前详情页菜单切换为“归档”。
3. 返回归档列表时，该记录应从归档列表移除。
4. 正常列表下次进入或刷新时应出现该记录。

### 8.4 归档记录列表入口

以下列表页右上角新增“归档记录”菜单入口：

1. 病历列表
2. 体检报告列表
3. 检查报告列表
4. 处方列表
5. 服用计划列表
6. 药品列表

进入后复用已有列表页面组件，只改变数据源查询参数：

```text
archived=true
```

页面标题建议：

| 业务 | 标题 |
|---|---|
| 病历 | 归档病历 |
| 体检 | 归档体检 |
| 检查报告 | 归档检查报告 |
| 处方 | 归档处方 |
| 服用计划 | 归档服用计划 |
| 药品 | 归档药品 |

### 8.5 列表页复用要求

归档列表应复用现有列表页的：

1. cell/card 样式。
2. 空状态样式。
3. 下拉刷新。
4. 分页或本地汇总数据处理逻辑。
5. 点击进入详情逻辑。

差异只保留：

1. 查询参数 `archived=true`。
2. 页面标题。
3. 空状态文案。
4. 是否展示新增按钮：归档列表不展示新增按钮。

归档列表空状态文案建议：

```text
暂无归档记录
```

### 8.6 药品与服用计划特殊规则

药品归档：

1. 药品从家庭药箱正常列表移除。
2. 药品详情可从归档药品列表进入。
3. 不自动删除或归档关联服用计划。
4. 创建或编辑服用计划选择药品时，默认不展示已归档药品。

服用计划归档：

1. 服用计划从正常用药计划列表移除。
2. 今日用药和提醒中心不应继续展示归档计划的未来提醒。
3. 历史服药记录保留。
4. 如果客户端有本地通知，需要在归档成功后取消该计划未来本地通知。

### 8.7 错误处理

| 场景 | 客户端处理 |
|---|---|
| 401 | 走现有登录失效流程 |
| 403 | Toast：`你没有权限操作此记录` |
| 404 | Toast：`记录不存在或已被删除`，返回上一页并刷新列表 |
| 网络失败 | Toast：`网络异常，请稍后重试` |
| 服务端校验失败 | 展示后端本地化错误文案 |

归档请求失败时，不应提前从本地列表移除记录。

### 8.8 客户端接口改造设计

客户端需要改造 `SparkMedicalQueryAPI` 和 `SparkMedicalWorkflowAPI`，把归档做成医疗资源的通用能力。

#### 8.8.1 归档查询参数模型

建议新增轻量枚举，统一生成服务端 `archived` 查询参数：

```swift
enum MedicalArchiveQuery: String, Sendable {
    case active = "false"
    case archived = "true"
    case all = "all"
}
```

默认值必须是 `.active`，保证旧调用不传参时仍查询正常记录。

#### 8.8.2 `SparkMedicalQueryAPI` 列表接口改造

文件：

```text
SparkClient/SparkClient/Projects/Core/Networking/API/Medical/MedicalQueryAPI.swift
```

以下方法需要新增 `archived: MedicalArchiveQuery = .active` 参数，并把它追加为 `URLQueryItem(name: "archived", value: archived.rawValue)`：

| 方法 | 业务 | 当前主要参数 | 新增参数 |
|---|---|---|---|
| `listMedicalCases` | 病历 | `memberID` | `archived` |
| `listMedicalCaseSummaries` | 病历摘要列表 | `memberID` | `archived` |
| `listHealthExamReports` | 体检报告 | `memberID` | `archived` |
| `listHealthExamReportsWithAttachments` | 体检报告列表 | `memberID` | `archived` |
| `listExaminationReports` | 检查报告 | `memberID` | `archived` |
| `listExaminationReportsWithAttachments` | 检查报告列表 | `memberID` | `archived` |
| `listMedicineBoxes` | 药品 | `memberID`、`medicineType`、`expireBefore`、`lowStock` | `archived` |
| `listPrescriptions` | 处方 | `memberID`、`medicalCaseID`、`status` | `archived` |
| `listMedicationPlans` | 服用计划 | `memberID`、`medicalCaseID`、`medicineBoxID`、`prescriptionID`、`status` | `archived` |

`listFamilyMedicineCabinet(memberID:)` 第一阶段不建议暴露归档参数，保持只返回正常药品。若后续需要家庭维度归档药箱页，再增加：

```swift
func listFamilyMedicineCabinet(memberID: Int, archived: MedicalArchiveQuery = .active)
```

#### 8.8.3 归档状态提交接口

文件：

```text
SparkClient/SparkClient/Projects/Core/Networking/API/Medical/MedicalWorkflowAPI.swift
```

现有通用方法已经支持：

```swift
func update<T: Decodable, B: Encodable & Sendable>(
    _ type: T.Type,
    kind: SparkMedicalResourceKind,
    id: Int,
    body: B,
    query: [URLQueryItem] = []
) async throws -> T
```

建议新增归档专用请求体：

```swift
nonisolated struct MedicalArchiveUpdatePayload: Encodable, Sendable {
    let isArchived: Bool
}
```

并建议增加统一封装，避免页面直接散落 `is_archived` PATCH：

```swift
func setArchived<T: Decodable>(
    _ type: T.Type,
    kind: SparkMedicalResourceKind,
    id: Int,
    archived: Bool
) async throws -> T
```

内部仍调用 `update(..., body: MedicalArchiveUpdatePayload(isArchived: archived))`。

编码注意：

1. `MedicalArchiveUpdatePayload.isArchived` 需要编码为后端字段 `is_archived`。
2. 客户端不得提交 `archived_at`，归档时间由服务端写入。
3. 写操作必须禁用 ETag，沿用现有 `update` 的高优先级串行写入。
4. 当前项目 `JSONEncoder.medicalAPI` 使用 snake_case 编码策略，字段命名为 `isArchived` 时会自动编码为 `is_archived`。
5. 如果实现者为 `MedicalArchiveUpdatePayload` 手写 `CodingKeys`，必须显式映射 `case isArchived = "is_archived"`。

#### 8.8.4 目标资源枚举

文件：

```text
SparkClient/SparkClient/Projects/Core/Networking/API/Medical/SparkMedicalResourceKind.swift
```

当前已包含本工单需要的资源：

```text
cases
health-exam-reports
examination-reports
medicine-boxes
prescriptions
medication-plans
```

无需新增枚举值，但归档服务需要限制只允许这些 kind 调用，避免误归档症状、手术、随访、明细行等非目标对象。

### 8.9 客户端数据模型改造文件

以下远端响应模型需要增加：

```swift
var isArchived: Bool = false
var archivedAt: Date?
```

文件：

```text
SparkClient/SparkClient/Projects/Core/Networking/API/Medical/MedicalSyncAPI.swift
```

必须改造的结构体：

| 结构体 | 业务 |
|---|---|
| `RemoteMedicalCase` | 病历详情 |
| `RemoteMedicalCaseSummary` | 病历列表 |
| `RemoteHealthExamReport` | 体检详情 |
| `RemoteHealthExamReportWithAttachments` | 体检列表 |
| `RemoteExaminationReport` | 检查报告详情 |
| `RemoteExaminationReportWithAttachments` | 检查报告列表 |
| `RemotePrescription` | 处方 |
| `RemoteMedicationPlan` | 服用计划 |
| `RemoteMedicineBox` | 药品 |

如页面仍使用 Core Domain 实体，也需要同步补字段：

```text
SparkClient/SparkClient/Projects/Core/Domain/Entities/MedicalCase.swift
SparkClient/SparkClient/Projects/Core/Domain/Entities/MedicalReport.swift
SparkClient/SparkClient/Projects/Core/Domain/Entities/MedicineBox.swift
SparkClient/SparkClient/Projects/Core/Domain/Entities/MedicationPlan.swift
```

如果某些 Domain 实体已经不参与当前医疗列表详情链路，可只做兼容补字段，不新增业务逻辑。

### 8.10 客户端归档服务建议

建议新增统一服务文件：

```text
SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Shared/MedicalArchiveMutationService.swift
```

职责：

1. 根据资源类型调用 `workflowAPI.setArchived`。
2. 返回更新后的远端对象。
3. 统一处理“归档”和“取消归档”的 loading 防重复提交。
4. 统一提供本地化成功/失败文案 key。
5. 为服用计划归档预留本地通知取消 hook。

建议接口形态：

```swift
struct MedicalArchiveMutationService: Sendable {
    let workflowAPI: SparkMedicalWorkflowAPI

    func setArchived<T: Decodable>(
        _ type: T.Type,
        kind: SparkMedicalResourceKind,
        id: Int,
        archived: Bool
    ) async throws -> T
}
```

### 8.11 客户端页面改造文件

#### 8.11.1 列表页入口与归档列表

以下列表页需要右上角新增“归档记录”入口，并支持复用当前列表组件加载 `archived=true`：

| 业务 | 文件 | 改造点 |
|---|---|---|
| 病历 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/MedicalCases/MedicalCasesListPage.swift` | 新增归档记录入口；列表初始化支持归档模式；刷新调用 `listMedicalCaseSummaries(archived:)` |
| 体检 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/HealthExamReports/HealthExamReportsListPage.swift` | 新增归档记录入口；刷新调用 `listHealthExamReportsWithAttachments(archived:)` |
| 检查报告 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/ExaminationReports/ExaminationReportsListPage.swift` | 新增归档记录入口；刷新调用 `listExaminationReportsWithAttachments(archived:)` |
| 处方/服用计划 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicationsListPage.swift` | 新增归档记录入口；处方和计划分别支持 `archived=true`；归档模式不展示新增入口 |
| 药品 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicineBox/MedicineBoxListPage.swift` | 新增归档记录入口；个人药箱调用 `listMedicineBoxes(archived:)` |
| 家庭药箱 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicineBox/FamilyMedicineCabinetPage.swift` | 正常模式继续只展示未归档药品；如入口指向归档药品，建议跳转 `MedicineBoxListPage` 的归档模式 |

建议为列表页增加统一模式：

```swift
enum MedicalArchiveListMode: Sendable {
    case active
    case archived
}
```

模式影响：

1. 页面标题。
2. 查询参数。
3. 空状态文案。
4. 是否展示新增/上传按钮。
5. 详情页回调后从当前列表移除还是更新。

#### 8.11.2 详情页归档/取消归档

以下详情页右上角菜单需要接入归档服务：

| 业务 | 文件 | 当前相关能力 | 改造点 |
|---|---|---|---|
| 病历 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/MedicalCases/MedicalCaseDetail/MedicalCaseDetailPage.swift` | 已有右上角菜单和删除逻辑 | 增加归档/取消归档菜单、二次确认、成功回调 |
| 体检 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/HealthExamReports/HealthExamReportDetailPage.swift`、`ExamReportCard.swift` | 体检卡片/详情展示 | 增加详情态归档入口；如果卡片内承载详情菜单，也需同步 |
| 检查报告 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/ExaminationReports/ExaminationReportDetailPage.swift`、`LabReportCard.swift`、`ExaminationReportSummaryDetailPage.swift` | 已有分享/删除菜单 | 增加归档/取消归档菜单、二次确认、成功回调 |
| 处方 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicationPrescriptionDetailPage.swift` | 已有删除弹窗 | 增加归档/取消归档菜单；不级联归档计划 |
| 服用计划 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicationPlanDetailPage.swift` | 已有删除逻辑 | 增加归档/取消归档菜单；归档成功后取消未来本地通知 |
| 药品 | `SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicineBox/MedicineBoxDetailPage.swift` | 已有分享/删除菜单 | 增加归档/取消归档菜单、二次确认、成功回调 |

详情页需要新增状态：

```swift
@State private var showingArchiveConfirm = false
@State private var isUpdatingArchiveState = false
```

菜单文案由当前对象 `isArchived` 决定：

```text
isArchived=false -> 归档
isArchived=true  -> 取消归档
```

#### 8.11.3 本地列表与缓存回写

归档状态更新成功后需要更新当前页面数据：

1. 正常列表中归档成功：从当前列表移除该对象。
2. 归档列表中取消归档成功：从当前列表移除该对象。
3. 详情页保留当前对象时，更新 `isArchived/archivedAt/updatedAt`。
4. 回写 `RemoteMemberCompleteData` 内对应数组，避免返回首页后旧数据闪回。

涉及文件：

```text
SparkClient/SparkClient/Projects/Features/Home/Presentation/HomeMedicalListsView.swift
SparkClient/SparkClient/Projects/Features/Home/Presentation/HomeMedicalRouteSupport.swift
SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Shared/MedExamDetailLazyLoadViewModel.swift
SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicineBox/FamilyMedicineCabinetViewModel.swift
```

### 8.12 本地化文案文件

需要新增中英文文案：

```text
SparkClient/SparkClient/Projects/App/Resources/zh-Hans.lproj/Localizable.strings
SparkClient/SparkClient/Projects/App/Resources/en.lproj/Localizable.strings
```

建议 key：

```text
medical.archive.menu.archive
medical.archive.menu.unarchive
medical.archive.confirm.archive.title
medical.archive.confirm.archive.message
medical.archive.confirm.archive.action
medical.archive.confirm.unarchive.title
medical.archive.confirm.unarchive.message
medical.archive.confirm.unarchive.action
medical.archive.toast.archived
medical.archive.toast.unarchived
medical.archive.list.entry
medical.archive.list.empty
medical.archive.list.medical_cases.title
medical.archive.list.health_exam_reports.title
medical.archive.list.examination_reports.title
medical.archive.list.prescriptions.title
medical.archive.list.medication_plans.title
medical.archive.list.medicine_boxes.title
```

### 8.13 客户端状态机

归档操作建议按统一状态机处理，避免重复点击、失败误删和列表闪动：

| 状态 | 说明 | 可触发动作 |
|---|---|---|
| `idle` | 默认状态 | 打开确认弹窗 |
| `confirmingArchive` | 展示归档确认 | 取消、确认归档 |
| `confirmingUnarchive` | 展示取消归档确认 | 取消、确认恢复 |
| `submitting` | 接口提交中 | 禁用菜单按钮 |
| `succeeded` | 服务端成功返回 | 更新详情对象、列表和缓存 |
| `failed` | 服务端或网络失败 | 保持原对象状态，展示错误 |

实现约束：

1. 进入 `submitting` 后，右上角菜单项置灰或隐藏，防止重复提交。
2. 成功前不得从列表移除记录。
3. 成功响应必须以服务端返回对象为准，不用本地猜测 `archivedAt`。
4. 如果详情页持有的是列表摘要对象，成功后只更新摘要对象已有字段；下次进入详情再拉完整详情。
5. 如果用户在提交中返回页面，任务完成后只回调仍然存在的上层列表，不强行弹回已经销毁的页面。

### 8.14 客户端缓存与 ETag 处理

归档是写操作，成功后必须主动处理本地缓存，否则服务端虽然已更新，客户端可能因为 ETag 或首页缓存继续显示旧数据。

#### 8.14.1 列表缓存处理

正常列表归档成功：

```text
active list: remove(id)
archived list: 如果当前已加载，可 insert/update(serverObject)
completeData: remove from active array
```

归档列表取消归档成功：

```text
archived list: remove(id)
active list: 如果当前已加载，可 insert/update(serverObject)
completeData: insert/update active array，或标记下次刷新
```

建议第一期采用简单策略：

1. 当前页面立即按成功结果更新。
2. 其他未展示页面只做脏标记。
3. 用户返回或下次进入时重新拉取对应列表。

#### 8.14.2 ETag 失效策略

当前 `SparkMedicalWorkflowAPI.update` 不使用 ETag，但读取列表会使用 ETag。归档成功后建议触发对应列表刷新或清理相关 ETag：

| 资源 | 需要刷新/失效 |
|---|---|
| 病历 | `cases archived=false`、`cases archived=true`、`complete-data` |
| 体检 | `health-exam-reports archived=false/true`、`complete-data` |
| 检查报告 | `examination-reports archived=false/true`、`complete-data` |
| 处方 | `prescriptions archived=false/true`、`complete-data` |
| 服用计划 | `medication-plans archived=false/true`、提醒计划接口、`complete-data` |
| 药品 | `medicine-boxes archived=false/true`、家庭药箱汇总、`complete-data` |

如果当前 ETagStore 没有按资源清理能力，页面层在归档成功后应直接用服务端返回对象更新内存态，并在下一次进入页面时发起普通刷新。

#### 8.14.3 首页 complete-data 回写

`RemoteMemberCompleteData` 中的数组默认只代表正常业务列表。归档成功后：

1. `medicalCases` 移除对应病历。
2. `healthExamReports` 移除对应体检报告。
3. `examinationReports` 移除对应检查报告。
4. `medicineBoxes/familyMedicineBoxes` 移除对应药品。
5. `prescriptions` 移除对应处方。
6. `medicationPlans` 移除对应服用计划。
7. `medicationSummary` 需要重新计算或等待下次服务端刷新。

取消归档成功后，若当前没有完整排序上下文，可以只标记 `complete-data` 需要刷新，不强行插入首页缓存，避免顺序和统计不准确。

### 8.15 客户端导航与路由细节

归档列表复用现有列表页时，建议使用显式模式参数，不建议通过标题字符串判断：

```swift
struct MedicalCasesListPage: View {
    let archiveMode: MedicalArchiveListMode
}
```

路由建议：

```text
正常列表 -> 详情 -> 归档成功 -> 详情保留，返回列表时列表已移除
正常列表 -> 归档记录入口 -> 归档列表 -> 详情 -> 取消归档成功 -> 返回归档列表时列表已移除
```

归档列表的详情页也应接收 `archiveMode` 或 `onArchiveStateChanged` 回调，让详情页知道成功后如何通知上层列表。

### 8.16 客户端本地通知联动

服用计划归档成功后，客户端需要取消该计划未来本地通知。建议接入：

```text
SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicationNotification/MedicationReminderNotificationManager.swift
SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicationNotification/MedicationReminderSyncCoordinator.swift
SparkClient/SparkClient/Projects/Features/Home/Presentation/MedicalLists/Medications/MedicationNotification/MedicationReminderPreferencesStore.swift
```

处理规则：

1. 归档服用计划成功后，取消该 `plan.id` 对应的未来本地通知。
2. 本地提醒授权记录是否删除不在本工单强制要求内，建议保留偏好，取消归档后可重新同步。
3. 取消归档服用计划后，如果 `reminderEnabled=true` 且 `status=active`，下次提醒同步应重新编译通知。
4. 如果取消通知失败，不回滚服务端归档状态，但需要记录日志并提示用户可重新打开提醒页同步。

### 8.17 客户端并发与一致性

需要处理以下边界：

1. 同一详情页连续点击归档/取消归档：`isUpdatingArchiveState=true` 时拒绝第二次提交。
2. 多端同时操作：以最后一次服务端响应为准；客户端刷新后同步最新状态。
3. 归档后立即删除：允许，但删除接口仍按现有软删除逻辑处理。
4. 删除后再取消归档：服务端应返回 404，客户端提示记录不存在或已删除。
5. 离线或弱网：不做离线队列，失败后保持原状态。

### 8.18 客户端测试建议

建议补充单元或轻量集成测试：

| 测试对象 | 用例 |
|---|---|
| `MedicalArchiveQuery` | `.active/.archived/.all` 生成正确 query value |
| `MedicalArchiveUpdatePayload` | `isArchived=true` 编码为 `is_archived=true` |
| `SparkMedicalQueryAPI` | 六类 list 方法携带 `archived=true` |
| `MedicalArchiveMutationService` | 只允许目标资源 kind；非目标 kind 抛错或拒绝 |
| 列表 ViewModel | 正常列表归档成功后 remove；归档列表取消归档后 remove |
| 详情页状态 | 已归档对象显示“取消归档”；正常对象显示“归档” |
| 服用计划 | 归档成功后触发取消未来本地通知 |

UI 手工回归至少覆盖：

1. 正常列表进入详情归档。
2. 归档列表进入详情取消归档。
3. 网络失败时列表不变化。
4. 无权限时展示错误。
5. 归档服用计划后不再收到未来本地通知。

## 9. 接口契约示例

### 9.1 查询正常药品

```http
GET /medical/medicine-boxes/?member_id=123
```

等价于：

```http
GET /medical/medicine-boxes/?member_id=123&archived=false
```

### 9.2 查询归档药品

```http
GET /medical/medicine-boxes/?member_id=123&archived=true
```

### 9.3 归档药品

```http
PATCH /medical/medicine-boxes/456/
Content-Type: application/json

{
  "is_archived": true
}
```

响应：

```json
{
  "code": 0,
  "msg": "updated",
  "data": {
    "id": 456,
    "is_archived": true,
    "archived_at": "2026-07-14T10:00:00+08:00",
    "updated_at": "2026-07-14T10:00:00+08:00"
  }
}
```

### 9.4 取消归档

```http
PATCH /medical/medicine-boxes/456/
Content-Type: application/json

{
  "is_archived": false
}
```

响应：

```json
{
  "code": 0,
  "msg": "updated",
  "data": {
    "id": 456,
    "is_archived": false,
    "archived_at": null,
    "updated_at": "2026-07-14T10:05:00+08:00"
  }
}
```

### 9.5 六类资源接口矩阵

| 业务 | 查询正常列表 | 查询归档列表 | 归档/取消归档 |
|---|---|---|---|
| 病历 | `GET /medical/cases/?member_id={id}` | `GET /medical/cases/?member_id={id}&archived=true` | `PATCH /medical/cases/{id}/` |
| 体检 | `GET /medical/health-exam-reports/?member_id={id}` | `GET /medical/health-exam-reports/?member_id={id}&archived=true` | `PATCH /medical/health-exam-reports/{id}/` |
| 检查报告 | `GET /medical/examination-reports/?member_id={id}` | `GET /medical/examination-reports/?member_id={id}&archived=true` | `PATCH /medical/examination-reports/{id}/` |
| 处方 | `GET /medical/prescriptions/?member_id={id}` | `GET /medical/prescriptions/?member_id={id}&archived=true` | `PATCH /medical/prescriptions/{id}/` |
| 服用计划 | `GET /medical/medication-plans/?member_id={id}` | `GET /medical/medication-plans/?member_id={id}&archived=true` | `PATCH /medical/medication-plans/{id}/` |
| 药品 | `GET /medical/medicine-boxes/?member_id={id}` | `GET /medical/medicine-boxes/?member_id={id}&archived=true` | `PATCH /medical/medicine-boxes/{id}/` |

如果客户端实际走统一资源入口 `/api/v1/medical/resources/?kind=...`，则保持现有 `kind` 参数不变，只追加 `archived=true/false/all`：

```http
GET /api/v1/medical/resources/?kind=medicine-boxes&member_id=123&archived=true
PATCH /api/v1/medical/resources/456/?kind=medicine-boxes
```

PATCH 请求体统一为：

```json
{
  "is_archived": true
}
```

### 9.6 错误码与客户端文案

| HTTP | `msg` 建议 | 客户端文案 |
|---|---|---|
| 400 | `invalid_archived_param` | 查询参数异常，请稍后重试 |
| 400 | `archive_status_required` | 归档状态缺失，请稍后重试 |
| 403 | `permission_denied` | 你没有权限操作此记录 |
| 404 | `not_found` / `record_not_found` | 记录不存在或已被删除 |
| 409 | `archive_state_conflict` | 记录状态已变化，请刷新后重试 |

第一期可以不新增 409。如果服务端采用幂等更新，重复归档或重复取消归档返回 200 即可。

## 10. 实施拆分

### 10.1 服务端任务

1. 在 `MedicalBaseModel` 增加 `is_archived`、`archived_at`。
2. 生成并检查数据库迁移。
3. 在序列化器中为目标资源暴露 `is_archived`、`archived_at`。
4. 在基础查询层支持 `archived` 查询参数。
5. 在更新逻辑中统一处理 `is_archived` 与 `archived_at`。
6. 汇总接口和特殊服务查询补充 `is_archived=false`。
7. 用药提醒、今日用药、药箱汇总排除归档记录。
8. 补充接口测试。

### 10.2 客户端任务

1. 目标资源 DTO / Domain Model 增加 `isArchived`、`archivedAt`。
2. 网络层支持查询参数 `archived`。
3. 目标详情页右上角菜单新增归档/取消归档。
4. 增加二次确认弹窗。
5. 实现归档状态 `PATCH` 提交。
6. 正常列表新增“归档记录”入口。
7. 归档记录列表复用现有列表组件。
8. 归档成功后刷新对应列表、详情和成员汇总缓存。
9. 服用计划归档成功后取消未来本地通知。
10. 补充本地化文案。

### 10.3 推荐开发顺序

1. 服务端先加字段和迁移，只暴露响应字段，不改变查询结果。
2. 服务端实现 `archived` 参数和 PATCH 归档更新。
3. 服务端补汇总接口、药箱汇总、提醒接口过滤。
4. 客户端先补 DTO 解码字段，确保旧页面不受影响。
5. 客户端补 `MedicalQueryAPI` 的 `archived` 参数和 `setArchived` 写接口。
6. 客户端先完成一类资源的归档闭环，建议从药品或病历开始。
7. 抽出 `MedicalArchiveMutationService` 和列表模式后，横向复制到其余资源。
8. 最后处理服用计划本地通知、归档列表入口、本地化和测试。

### 10.4 灰度与回滚方案

服务端字段默认值为 `false`，因此迁移上线后旧客户端仍能正常工作。

灰度建议：

1. 后端先上线字段和兼容响应。
2. 客户端发版前，服务端不在默认列表返回归档数据变更之外做破坏性改动。
3. 客户端可用本地开关或远程配置控制归档入口是否展示。
4. 如发现问题，客户端隐藏入口即可停止新增归档操作，已归档数据仍可通过服务端脚本或后台恢复。

回滚注意：

1. 已经归档的数据如果回滚到不支持归档过滤的服务端，可能重新出现在列表中。
2. 若需要完全回滚产品能力，不建议删除字段；保留字段并隐藏入口。
3. 如果误归档范围较大，服务端可以按 `archived_at` 时间窗口批量恢复。

## 11. 测试与验收

### 11.1 服务端验收

1. 新建目标资源时，`is_archived=false` 且 `archived_at=null`。
2. `PATCH is_archived=true` 后，响应返回 `is_archived=true` 和非空 `archived_at`。
3. `PATCH is_archived=false` 后，响应返回 `is_archived=false` 和 `archived_at=null`。
4. 不携带 `archived` 查询参数时，目标列表不返回归档记录。
5. 携带 `archived=true` 时，只返回归档记录。
6. 携带 `archived=all` 时，返回正常和归档记录。
7. 成员权限仍然生效，无权限用户不能归档或取消归档。
8. 软删除记录不出现在正常列表和归档列表。
9. 成员医疗汇总接口不返回归档病历、报告、处方、服用计划、药品。
10. 家庭药箱汇总不返回归档药品。
11. 今日用药和提醒相关接口不返回归档服用计划的未来任务。
12. 归档详情仍可通过 id 读取。

### 11.2 客户端验收

1. 六类详情页右上角均有归档入口。
2. 点击归档必须出现二次确认弹窗。
3. 确认归档后，请求服务端成功，详情菜单切换为“取消归档”。
4. 返回正常列表后，已归档记录不再展示。
5. 六类列表页右上角均可进入归档记录列表。
6. 归档记录列表只展示已归档数据。
7. 已归档记录进入详情页后，右上角菜单显示“取消归档”，不显示“归档”。
8. 点击“取消归档”必须出现二次确认弹窗。
9. 确认取消归档后，请求服务端成功，详情菜单切换为“归档”。
10. 取消归档后，该记录从归档列表移除，并可在正常列表中重新出现。
11. 网络失败或无权限时，本地列表状态不提前变更。
12. 旧服务端不返回归档字段时，客户端仍能正常解析已有列表。

### 11.3 联调验收矩阵

| 场景 | 服务端验证 | 客户端验证 |
|---|---|---|
| 正常列表归档病历 | `PATCH cases/{id}` 返回 `is_archived=true` | 病历从正常列表消失，详情菜单变为取消归档 |
| 归档列表恢复病历 | `PATCH cases/{id}` 返回 `is_archived=false` | 病历从归档列表消失，正常列表刷新后出现 |
| 归档药品 | 药箱列表和家庭药箱汇总不再返回该药品 | 家庭药箱不展示该药品，归档药品列表可查看 |
| 归档服用计划 | 提醒接口不再返回该计划 | 本地未来通知被取消 |
| 归档检查报告 | 检查报告正常列表不返回，详情仍可读取 | 从归档列表进入详情显示取消归档 |
| 无权限归档 | 返回 403 | 不移除列表项，提示无权限 |
| 归档后删除 | 删除接口成功软删除 | 归档列表移除，详情返回上一页 |
| 弱网失败 | 服务端无状态变化 | 本地状态保持原样 |

### 11.4 数据迁移验收

1. 所有新增字段默认值正确。
2. 已有数据迁移后均为 `is_archived=false`。
3. 数据库索引创建成功。
4. 迁移后正常列表数量与迁移前一致。
5. 手动归档一条记录后，正常列表数量减少 1，归档列表数量增加 1。
6. 取消归档后，两边数量恢复。

## 12. 风险与注意事项

1. `MedicalBaseModel` 加字段会影响多张表，迁移前需要确认线上表规模和迁移窗口。
2. 如果只在部分 ViewSet 过滤归档，首页汇总和普通列表会出现数据不一致，应优先沉到基础查询层和共享服务层。
3. 归档服用计划与本地通知有关，客户端和服务端都要停止未来提醒，避免用户归档后仍收到服药通知。
4. ETag 构建依赖 `updated_at`，归档和取消归档必须刷新 `updated_at`，否则客户端可能拿到 304。
5. 归档列表复用正常列表时，要避免误展示“新增”入口和正常列表专用空状态。
6. 归档药品不能进入默认选药列表，否则用户会在创建用药计划时选到已经收纳的历史药品。
7. 关联对象不做级联归档，避免误隐藏用户仍在使用的数据。

## 13. 建议上线顺序

1. 服务端先上线字段、迁移、响应字段，默认值不影响旧客户端。
2. 服务端上线列表过滤和归档更新能力。
3. 客户端上线模型字段兼容和正常列表默认行为验证。
4. 客户端上线详情归档操作。
5. 客户端上线归档记录列表入口。
6. 最后补充提醒、药箱、汇总接口的回归验证。

## 14. 需要产品确认的问题

1. 归档后的详情页是否允许继续编辑。
2. 归档后的分享链接是否继续有效。
3. 病历归档时，是否需要提示“关联处方、检查报告不会自动归档”。
4. 药品归档时，如果存在启用中的服用计划，是否需要额外提醒用户。
5. 归档列表是否需要支持再次删除。
