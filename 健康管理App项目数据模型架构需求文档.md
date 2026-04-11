# 健康管理App项目数据模型架构需求文档

**文档版本**：V2.2

**文档状态**：可编辑

**最后更新**：2026年04月

**技术栈**：Django ORM、关系型数据库

**项目定位**：SparkService 后端数据模型需求说明；字段、约束、索引与仓库 ORM 对齐。本文档各模型统一采用「项目/详情」摘要表 +「字段详细设计」五列表（字段名、数据类型、约束、索引、字段说明）。

---

# 一、文档总则

## 1.1 文档目的

定义 SparkService 数据模型架构、字段规范、约束与模块边界，作为需求、库表、接口与测试的依据。

## 1.2 适用范围

本仓库自研应用 `medical`、`accounts`、`ai_config`、`file_manager`、`backoffice`、`chat_sync`；不含 Django 内置表及第三方包表的逐字段说明。

## 1.3 术语说明

| 术语 | 说明 |
| --- | --- |
| 软删除 | `is_deleted` / `deleted_at`；`MedicalBaseModel` 默认管理器仅 `is_deleted=False` |
| `Member` | 家庭就诊成员，健康业务挂载主体 |
| `bundle_id` | 多见于 accounts 域，医疗业务表不冗余 |

## 1.4 设计原则摘要

用户与成员归属一致；用药等模型 `clean()` 防串数据；高频查询走 `Meta.indexes`；敏感字段按安全规范处理。

---

# 二、项目整体模块架构

| 模块分类 | Django 应用 | 主要模型 |
| --- | --- | --- |
| 医疗 | `medical` | 基类与软删除、`Member`、病历与子表、体检/检查/明细、用药三表、`ModelChangeLog`、`HealthMetricRecord` |
| 账户 | `accounts` | `AccountProfile`、`TrustedDevice`、`LoginAudit`、`SocialIdentity`、`EmailOTP`、`PhoneOTP`、销户与审计 |
| AI | `ai_config` | 场景绑定、厂商 Key、模型目录、Bootstrap、试用与策略条目 |
| 文件 | `file_manager` | `ManagedFile` |
| 后台 | `backoffice` | RBAC、`AdminAuditLog`、权限种子 |
| 聊天 | `chat_sync` | `ChatThread`、`ChatMessage` |

---

# 三、医疗域：非表类型与抽象基类

## 3.1 软删除查询集（SoftDeleteQuerySet）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `SoftDeleteQuerySet` |
| 数据库表名 | 无（非持久化类型） |
| 模型说明 | `QuerySet` 子类，为医疗模型提供软删除过滤语义 |
| 核心功能 | 1. `alive()`：`is_deleted=False`；2. `deleted()`：`is_deleted=True` |

#### 成员说明（非字段表）

| 成员/方法 | 说明 |
| --- | --- |
| `alive()` | 过滤未软删除行 |
| `deleted()` | 过滤已软删除行 |

---

## 3.2 软删除管理器（SoftDeleteManager）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `SoftDeleteManager` |
| 数据库表名 | 无（非持久化类型） |
| 模型说明 | `Manager` 子类，默认仅返回未软删除行 |
| 核心功能 | `get_queryset()` 等价 `SoftDeleteQuerySet.alive()` |

---

## 3.3 医疗模型抽象基类（MedicalBaseModel）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `MedicalBaseModel` |
| 数据库表名 | 无（`Meta.abstract = True`） |
| 模型说明 | 医疗业务模型公共字段与默认管理器；子类映射各自表 |
| 核心功能 | 1. 统一 `user` 归属与软删除；2. 默认 `objects` 排除已删；3. `soft_delete()` 单次标记删除 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `user` | `ForeignKey(User)` | `on_delete=CASCADE`，`related_name="%(class)s_items"` | 普通索引（`db_index=True`） | 数据所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引 | 软删除标记 |
| `deleted_at` | `DateTimeField` | `null=True`，`blank=True` | 无 | 删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add=True` | 普通索引 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now=True` | 普通索引 | 更新时间 |
| `objects` | `SoftDeleteManager` | 默认管理器 | 无 | 仅未删除 |
| `all_objects` | `Manager` | 备用管理器 | 无 | 含已删除 |

#### 元数据配置

- 方法：`soft_delete()` 已删除则返回；否则更新 `is_deleted`、`deleted_at`、`updated_at`。

---

# 四、医疗业务数据模型设计

## 4.1 家庭就诊成员（Member）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Member` |
| 数据库表名 | `medical_member` |
| 模型说明 | 账号下就诊成员（本人与亲属），病历/检查/体检/用药挂载主体。 |
| 核心功能 | 1. 人口学与过敏/慢病；2. 主档案优先展示；3. 与 `User` 多对一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除 |
| `deleted_at` | `DateTimeField` | 可空 | 无 | 删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `name` | `CharField(64)` | NOT NULL | 无 | 姓名 |
| `gender` | `CharField(16)` | `choices=Gender`，默认 `unknown` | 无 | 性别 male/female/unknown |
| `relationship` | `CharField(64)` | 默认 `self` | 无 | 与主账户关系 |
| `birth_date` | `DateField` | 可空 | 无 | 出生日期 |
| `blood_type` | `CharField(8)` | 可空 | 无 | 血型 |
| `allergies` | `JSONField` | `default=list` | 无 | 过敏史列表 |
| `chronic_conditions` | `JSONField` | `default=list` | 无 | 慢性病史列表 |
| `notes` | `TextField` | 可空 | 无 | 备注 |
| `avatar_url` | `CharField(512)` | 可空 | 无 | 头像 URL |
| `is_primary` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 是否主档案 |

#### 元数据配置

- 排序：`-is_primary`, `-updated_at`, `-id`。
- `__str__`：`姓名(关系)`。

---

## 4.2 病历主档（MedicalCase）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `MedicalCase` |
| 数据库表名 | `medical_medicalcase` |
| 模型说明 | 病历聚合根；临床细节在子表。 |
| 核心功能 | 1. 状态机草稿/提交/归档；2. 按成员与时间检索；3. 瘦身主档。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除 |
| `deleted_at` | `DateTimeField` | 可空 | 无 | 删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE`，`related_name=medical_cases` | 普通索引（`db_index=True`） | 所属成员 |
| `record_type` | `CharField(32)` | 默认 `custom` | 普通索引（`db_index=True`） | 病历类型字符串 |
| `status` | `PositiveSmallIntegerField` | `choices` 1草稿/2提交/3归档，默认1 | 普通索引（`db_index=True`） | 状态 |
| `title` | `CharField(255)` | 可空 | 无 | 标题 |
| `hospital_name` | `CharField(255)` | 可空 | 普通索引（`db_index=True`） | 医院名称 |
| `age_at_visit` | `PositiveSmallIntegerField` | 可空 | 无 | 就诊时年龄 |
| `diagnosis_summary` | `TextField` | 可空 | 无 | 诊断摘要 |
| `extra` | `JSONField` | `default=dict` | 无 | 扩展 |

#### 元数据配置

- 联合索引：`(member, is_deleted, created_at)`；`(member, record_type, is_deleted, created_at)`；`(member, status, is_deleted, created_at)`。
- 普通索引：`(hospital_name)`。
- 排序：`-created_at`, `-updated_at`, `-id`。

---

## 4.3 症状（Symptom）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Symptom` |
| 数据库表名 | `medical_symptom` |
| 模型说明 | 病历下症状条目，支持时长与部位。 |
| 核心功能 | 1. 关联病例与成员；2. 按部位检索。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `on_delete=CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除标记 |
| `deleted_at` | `DateTimeField` | `null=True` | 无 | 软删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=symptoms` |
| `medical_case` | `ForeignKey(MedicalCase)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=symptoms` |
| `name` | `CharField(128)` | NOT NULL | 无 | 症状名称 |
| `code` | `CharField(64)` | 可空 | 无 | 编码 |
| `severity` | `CharField(32)` | 可空 | 无 | 严重程度 |
| `started_at` | `DateTimeField` | 可空 | 无 | 起病时间 |
| `duration_value` | `PositiveIntegerField` | 可空 | 无 | 持续时长数值 |
| `duration_unit` | `CharField(16)` | 可空 | 无 | 持续时长单位 |
| `body_part` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 解剖部位 |
| `notes` | `TextField` | 可空 | 无 | 备注 |
| `extra` | `JSONField` | `default=dict` | 无 | 扩展 |

#### 元数据配置

- 联合索引：`(medical_case, created_at)`；`(member, medical_case, is_deleted, created_at)`。
- 普通索引：`(body_part)`。
- 排序：`-created_at`, `-updated_at`, `-id`。

---

## 4.4 就诊记录（Visit）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Visit` |
| 数据库表名 | `medical_visit` |
| 模型说明 | 门诊/急诊等就诊节点。 |
| 核心功能 | 1. 时间轴排序；2. 外部 `source_system_id` 幂等。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `on_delete=CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除标记 |
| `deleted_at` | `DateTimeField` | `null=True` | 无 | 软删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=visits` |
| `medical_case` | `ForeignKey(MedicalCase)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=visits` |
| `visit_type` | `CharField(32)` | 默认 `custom` | 无 | 就诊类型 |
| `visited_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 就诊时间 |
| `department` | `CharField(128)` | 可空 | 无 | 科室 |
| `doctor_name` | `CharField(128)` | 可空 | 无 | 医生 |
| `visit_no` | `CharField(64)` | 可空 | 无 | 就诊号 |
| `source_system_id` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 外部系统 ID |
| `notes` | `TextField` | 可空 | 无 | 备注 |
| `extra` | `JSONField` | `default=dict` | 无 | 扩展 |

#### 元数据配置

- 联合索引：`(medical_case, visited_at)`；`(member, medical_case, is_deleted, visited_at)`。
- 普通索引：`(source_system_id)`。
- 排序：`-visited_at`, `-updated_at`, `-id`。

---

## 4.5 手术记录（Surgery）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Surgery` |
| 数据库表名 | `medical_surgery` |
| 模型说明 | 手术/操作与质控字段。 |
| 核心功能 | 1. 关联病例；2. 外部幂等 ID。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `on_delete=CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除标记 |
| `deleted_at` | `DateTimeField` | `null=True` | 无 | 软删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=surgeries` |
| `medical_case` | `ForeignKey(MedicalCase)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=surgeries` |
| `procedure_name` | `CharField(255)` | NOT NULL | 无 | 术式名称 |
| `procedure_code` | `CharField(64)` | 可空 | 无 | 编码 |
| `site` | `CharField(128)` | 可空 | 无 | 部位 |
| `performed_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 手术时间 |
| `surgeon` | `CharField(128)` | 可空 | 无 | 术者 |
| `anesthesia_type` | `CharField(128)` | 可空 | 无 | 麻醉方式 |
| `incision_level` | `CharField(8)` | 可空 | 无 | 切口等级 |
| `asa_class` | `CharField(8)` | 可空 | 无 | ASA 分级 |
| `source_system_id` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 外部系统 ID |
| `notes` | `TextField` | 可空 | 无 | 备注 |
| `extra` | `JSONField` | `default=dict` | 无 | 扩展 |

#### 元数据配置

- 联合索引：`(medical_case, performed_at)`；`(member, medical_case, is_deleted, performed_at)`。
- 普通索引：`(source_system_id)`。
- 排序：`-performed_at`, `-updated_at`, `-id`。

---

## 4.6 随访（FollowUp）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `FollowUp` |
| 数据库表名 | `medical_followup` |
| 模型说明 | 随访计划与执行。 |
| 核心功能 | 1. 按病例状态列表；2. 关联成员与用户。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `on_delete=CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除标记 |
| `deleted_at` | `DateTimeField` | `null=True` | 无 | 软删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=follow_ups` |
| `medical_case` | `ForeignKey(MedicalCase)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=follow_ups` |
| `planned_at` | `DateTimeField` | 可空 | 无 | 计划时间 |
| `completed_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 完成时间 |
| `status` | `CharField(20)` | 默认 `initial` | 普通索引（`db_index=True`） | 随访状态 |
| `method` | `CharField(32)` | 可空 | 无 | 方式 |
| `outcome` | `TextField` | 可空 | 无 | 结果摘要 |
| `next_action` | `TextField` | 可空 | 无 | 下一步建议 |
| `extra` | `JSONField` | `default=dict` | 无 | 扩展 |

#### 元数据配置

- 联合索引：`(medical_case, status, completed_at)`；`(member, medical_case, is_deleted, completed_at)`。
- 排序：`-completed_at`, `-updated_at`, `-id`。

---

## 4.7 临床检查报告（ExaminationReport）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ExaminationReport` |
| 数据库表名 | `medical_examination_report` |
| 模型说明 | 临床检查主表（影像/功能/病理等）。 |
| 核心功能 | 1. 成员必填；2. 可选挂病历 `medical_record`；3. OCR 快照。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `on_delete=CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除标记 |
| `deleted_at` | `DateTimeField` | `null=True` | 无 | 软删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=examination_reports` |
| `medical_record` | `ForeignKey(MedicalCase)` | `SET_NULL` 可空 | 普通索引（`db_index=True`） | 可选病历，字段名 `medical_record` |
| `category` | `CharField(128)` | 可空 | 无 | 大类 |
| `sub_category` | `CharField(128)` | 可空 | 无 | 子类 |
| `item_name` | `CharField(255)` | NOT NULL | 无 | 项目名称 |
| `performed_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 检查时间 |
| `reported_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 报告时间 |
| `organization_name` | `CharField(255)` | 可空（`null`） | 无 | 机构名称 |
| `department_name` | `CharField(128)` | 可空 | 无 | 科室 |
| `doctor_name` | `CharField(128)` | 可空 | 无 | 医生 |
| `findings` | `TextField` | 可空 | 无 | 所见 |
| `impression` | `TextField` | 可空 | 无 | 结论 |
| `source` | `PositiveSmallIntegerField` | `choices` 1手工/2OCR | 无 | 来源 |
| `raw_ocr` | `JSONField` | 可空 | 无 | OCR 原始 |
| `status` | `PositiveSmallIntegerField` | `choices` 1–4 | 普通索引（`db_index=True`） | 草稿/完成/修订/废弃 |
| `extra` | `JSONField` | 可空 | 无 | 扩展 |

#### 元数据配置

- 联合索引：`(member, status, is_deleted)`；`(member, performed_at, is_deleted)`；`(member, reported_at, is_deleted)`。
- 排序：`-reported_at`, `-updated_at`, `-id`。

---

## 4.8 体检报告（HealthExamReport）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `HealthExamReport` |
| 数据库表名 | `medical_health_exam_report` |
| 模型说明 | 单次体检报告主表。 |
| 核心功能 | 1. 机构与报告号；2. 枚举体检类型与来源；3. 明细见 `MedExamDetail`。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `on_delete=CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除标记 |
| `deleted_at` | `DateTimeField` | `null=True` | 无 | 软删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=health_exam_reports` |
| `institution_name` | `CharField(255)` | 可空 | 无 | 体检机构 |
| `report_no` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 报告编号 |
| `exam_date` | `DateField` | 可空 | 普通索引（`db_index=True`） | 体检日期 |
| `exam_type` | `PositiveSmallIntegerField` | `choices` 1–4 | 无 | 体检类型 |
| `summary` | `TextField` | 可空 | 无 | 综述/结论 |
| `source` | `PositiveSmallIntegerField` | `choices` 1–3 | 无 | 来源 |
| `raw_ocr` | `JSONField` | 可空 | 无 | OCR 原始 |
| `status` | `PositiveSmallIntegerField` | `choices` 1–3 | 普通索引（`db_index=True`） | 草稿/完成/校验 |
| `extra` | `JSONField` | 可空 | 无 | 扩展 |

#### 元数据配置

- 联合索引：`(member, exam_date, is_deleted)`；`(member, status, is_deleted)`。
- 排序：`-exam_date`, `-updated_at`, `-id`。

---

## 4.9 医技结果明细（MedExamDetail）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `MedExamDetail` |
| 数据库表名 | `medical_med_exam_detail` |
| 模型说明 | 体检与临床检查共用行级结果；多态挂载 `business_type`+`business_id`。 |
| 核心功能 | 1. 强绑 `member`；2. 与父记录 `member` 一致须应用层校验；3. 无 `MedicalBaseModel`。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `business_type` | `CharField(32)` | `choices` health_exam_report / examination_report | 普通索引（`db_index=True`） | 父业务类型 |
| `business_id` | `PositiveBigIntegerField` | NOT NULL | 普通索引（`db_index=True`） | 父主键 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=med_exam_details` |
| `category` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 大类 |
| `sub_category` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 子类 |
| `item_name` | `CharField(255)` | NOT NULL | 无 | 项目名称 |
| `item_code` | `CharField(64)` | 可空 | 无 | 项目编码 |
| `result_value` | `CharField(255)` | 可空 | 无 | 结果值 |
| `unit` | `CharField(64)` | 可空 | 无 | 单位 |
| `reference_range` | `CharField(255)` | 可空 | 无 | 参考范围 |
| `flag` | `CharField(16)` | 可空 | 无 | 异常标识 |
| `result_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 结果时间 |
| `modality` | `CharField(32)` | 可空 | 无 | 影像模态 |
| `body_part` | `CharField(128)` | 可空 | 无 | 部位 |
| `diagnosis` | `TextField` | 可空 | 无 | 诊断文本 |
| `extra` | `JSONField` | 可空 | 无 | 扩展 |
| `sort_order` | `PositiveIntegerField` | 默认 0 | 无 | 展示顺序 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除（无 `deleted_at`） |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |

#### 元数据配置

- 联合索引：`(business_type, business_id, is_deleted)`；`(member, is_deleted)`；`(category, sub_category, is_deleted)`；`(business_type, business_id, sort_order)`。
- 排序：`sort_order`, `-updated_at`, `-id`。

---

## 4.10 处方批次（PrescriptionBatch）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `PrescriptionBatch` |
| 数据库表名 | `medical_prescription_batch` |
| 模型说明 | 处方/用药方案批次头。 |
| 核心功能 | 1. `clean()` 防跨用户/跨成员；2. `save()` `full_clean()`；3. `batch_no` 空串存 `NULL`。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除 |
| `deleted_at` | `DateTimeField` | 可空 | 无 | 删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=prescription_batches` |
| `medical_case` | `ForeignKey(MedicalCase)` | `SET_NULL` 可空 | 普通索引（`db_index=True`） | 可选来源病历 |
| `prescriber_name` | `CharField(128)` | 可空 | 无 | 开方医生 |
| `institution_name` | `CharField(255)` | 可空 | 无 | 机构 |
| `prescribed_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 开方时间 |
| `diagnosis` | `TextField` | 可空 | 无 | 诊断摘要 |
| `batch_no` | `CharField(128)` | 可空，可 `NULL` | 普通索引（`db_index=True`） | 批次号，非全局唯一 |
| `status` | `CharField(20)` | `choices` active 等 | 普通索引（`db_index=True`） | 批次状态 |
| `auditor_name` | `CharField(128)` | 可空 | 无 | 审核人 |
| `audited_at` | `DateTimeField` | 可空 | 无 | 审核时间 |
| `extra` | `JSONField` | `default=dict` | 无 | 扩展 |

#### 元数据配置

- 联合索引：`(user, member, is_deleted, prescribed_at)`。
- 普通索引：`(medical_case)`；`(batch_no)`。
- 排序：`-prescribed_at`, `-updated_at`, `-id`。

---

## 4.11 用药药品行（Medication）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Medication` |
| 数据库表名 | `medical_medication` |
| 模型说明 | 批次下药品与用法、提醒规则。 |
| 核心功能 | 1. `clean()` 与批次成员一致；2. 服务任务引擎生成计划。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除 |
| `deleted_at` | `DateTimeField` | 可空 | 无 | 删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=medications` |
| `batch` | `ForeignKey(PrescriptionBatch)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=medications` |
| `generic_name` | `CharField(255)` | 可空 | 无 | 通用名 |
| `brand_name` | `CharField(255)` | 可空 | 无 | 品牌名 |
| `drug_name` | `CharField(255)` | NOT NULL | 无 | 展示名 |
| `dosage_form` | `CharField(64)` | 可空 | 无 | 剂型 |
| `strength` | `CharField(128)` | 可空 | 无 | 规格 |
| `route` | `CharField(64)` | 可空 | 无 | 给药途径 |
| `dose_per_time` | `CharField(64)` | 可空 | 无 | 单次剂量文本 |
| `dose_value` | `DecimalField(10,3)` | 可空 | 无 | 单次剂量数值 |
| `dose_unit` | `CharField(32)` | 可空 | 无 | 剂量单位 |
| `frequency_code` | `CharField(64)` | 可空 | 无 | 频次编码 |
| `period` | `CharField(16)` | 可空 | 无 | 周期 |
| `times_per_period` | `PositiveSmallIntegerField` | 可空 | 无 | 每周期次数 |
| `frequency_text` | `CharField(255)` | 可空 | 无 | 频次文案 |
| `duration_days` | `PositiveIntegerField` | 可空 | 无 | 疗程天 |
| `instructions` | `TextField` | 可空 | 无 | 用药说明 |
| `reminder_enabled` | `BooleanField` | 默认 True | 无 | 是否提醒 |
| `reminder_times` | `JSONField` | `default=list` | 无 | 提醒时刻列表 |
| `sort_order` | `PositiveIntegerField` | 默认 0 | 无 | 批次内顺序 |
| `extra` | `JSONField` | `default=dict` | 无 | 扩展 |

#### 元数据配置

- 联合索引：`(batch, sort_order)`；`(user, member, is_deleted, created_at)`。
- 排序：`sort_order`, `-updated_at`, `-id`。

---

## 4.12 服药打卡（MedicationTakenRecord）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `MedicationTakenRecord` |
| 数据库表名 | `medical_medication_taken_record` |
| 模型说明 | 单次应服/已服/漏服记录。 |
| 核心功能 | 1. 唯一约束防重复计划；2. `clean()` 归属一致。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除 |
| `deleted_at` | `DateTimeField` | 可空 | 无 | 删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `member` | `ForeignKey(Member)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=medication_taken_records` |
| `medication` | `ForeignKey(Medication)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=taken_records` |
| `scheduled_at` | `DateTimeField` | NOT NULL | 普通索引（`db_index=True`） | 计划服药时间 |
| `taken_at` | `DateTimeField` | 可空 | 无 | 实际打卡时间 |
| `status` | `CharField(20)` | `choices` scheduled/taken/skipped/snoozed | 普通索引（`db_index=True`） | 状态 |
| `dose_sequence` | `PositiveSmallIntegerField` | 默认 1 | 无 | 当日第几次 |
| `actual_dose` | `CharField(64)` | 可空 | 无 | 实际剂量描述 |
| `timezone` | `CharField(64)` | 默认 UTC | 普通索引（`db_index=True`） | 时区 |
| `notes` | `TextField` | 可空 | 无 | 备注 |
| `extra` | `JSONField` | `default=dict` | 无 | 扩展 |

#### 元数据配置

- **唯一约束**：`(medication, scheduled_at, dose_sequence)` → `uniq_medication_schedule_sequence`。
- 联合索引：`(medication, scheduled_at, status)`；`(user, member, scheduled_at, status)`。
- 排序：`-scheduled_at`, `-updated_at`, `-id`。

---

## 4.13 模型变更日志（ModelChangeLog）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ModelChangeLog` |
| 数据库表名 | `medical_model_change_log` |
| 模型说明 | 医疗域通用审计（Who/When/What）。 |
| 核心功能 | 1. 不继承 `MedicalBaseModel`；2. 可选关联成员。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=medical_change_logs` |
| `member` | `ForeignKey(Member)` | `SET_NULL` 可空 | 无 | `related_name=change_logs`（无单列索引） |
| `entity` | `CharField(64)` | NOT NULL | 普通索引（`db_index=True`） | 实体类型 |
| `entity_id` | `PositiveBigIntegerField` | NOT NULL | 普通索引（`db_index=True`） | 实体主键 |
| `action` | `CharField(32)` | NOT NULL | 普通索引（`db_index=True`） | 动作 |
| `from_status` | `CharField(32)` | 可空 | 无 | 变更前状态 |
| `to_status` | `CharField(32)` | 可空 | 无 | 变更后状态 |
| `changed_fields` | `JSONField` | `default=dict` | 无 | 字段差异 |
| `trace_id` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 追踪 ID |
| `operator` | `CharField(128)` | 可空 | 无 | 操作者描述 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |

#### 元数据配置

- 排序：`-created_at`, `-id`。

---

## 4.14 健康指标记录（HealthMetricRecord）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `HealthMetricRecord` |
| 数据库表名 | `medical_healthmetricrecord` |
| 模型说明 | 按 `profile_client_uid` 的指标时间序列；不外键 `Member`。 |
| 核心功能 | 1. 与用户绑定；2. 客户端档案 UUID 维度同步。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 普通索引（`db_index=True`） | 所属用户 |
| `is_deleted` | `BooleanField` | `default=False` | 普通索引（`db_index=True`） | 软删除 |
| `deleted_at` | `DateTimeField` | 可空 | 无 | 删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |
| `profile_client_uid` | `UUIDField` | NOT NULL | 普通索引（`db_index=True`） | 客户端档案稳定 ID |
| `metric_type` | `CharField(64)` | NOT NULL | 普通索引（`db_index=True`） | 指标类型 |
| `value` | `FloatField` | 默认 0 | 无 | 数值 |
| `unit` | `CharField(32)` | 默认空 | 无 | 单位 |
| `recorded_at` | `DateTimeField` | NOT NULL | 普通索引（`db_index=True`） | 采样时刻 |
| `note` | `TextField` | 可空 | 无 | 备注 |

#### 元数据配置

- 无 `Meta.indexes` 声明（除字段 `db_index`）；排序：`-recorded_at`, `-updated_at`, `-id`。

---

# 五、账户与认证模块（accounts）

## 5.1 用户扩展资料（AccountProfile）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AccountProfile` |
| 数据库表名 | `accounts_accountprofile` |
| 模型说明 | Django `User` 一对一业务扩展。 |
| 核心功能 | 1. 手机号等扩展字段。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `OneToOneField(User)` | `CASCADE`，`related_name=profile` | 无 | 用户（ORM 通常为 user_id 唯一） |
| `phone_number` | `CharField(32)` | 可空 | 普通索引（`db_index=True`） | 手机号 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- `__str__`：`profile:{user_id}`。

---

## 5.2 可信设备（TrustedDevice）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `TrustedDevice` |
| 数据库表名 | `accounts_trusteddevice`（实现以迁移为准；字段升级后或需调整长度/索引） |
| 模型说明 | 用户可信设备全量信息，支持多应用包隔离、推送令牌与设备风控。 |
| 核心功能 | 1. `bundle_id` + `device_id` 定位设备；2. APNs `push_token` 与通知开关；3. 软硬件与本地化上下文；4. 验证状态与时间轴（`first_seen` / `last_seen`）。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | 自增主键 | PRIMARY KEY | 主键索引 | 表自增主键 |
| `user` | `ForeignKey` | 关联 `User` 表、`on_delete=CASCADE`、`NOT NULL` | 无 | 关联系统用户，用户删除时级联删除设备信息 |
| `bundle_id` | `CharField(255)` | `NOT NULL` | 普通索引 | 应用包标识符，实现多应用设备隔离 |
| `device_id` | `CharField(255)` | `NOT NULL` | 普通索引 | 设备唯一标识符 |
| `push_token` | `CharField(512)` | `blank=True`、`default=""` | 无 | APNs 推送通知设备令牌 |
| `notifications_enabled` | `BooleanField` | `default=False` | 无 | 是否开启推送通知 |
| `app_version` | `CharField(50)` | `blank=True`、`default=""` | 无 | 应用版本号 |
| `build_version` | `CharField(50)` | `blank=True`、`default=""` | 无 | 应用构建版本号 |
| `bundle_identifier` | `CharField(255)` | `blank=True`、`default=""` | 无 | 客户端 Bundle ID |
| `platform` | `CharField(20)` | `blank=True`、`default=""` | 无 | 平台类型，如 iOS / tvOS / watchOS / macOS |
| `system_version` | `CharField(50)` | `blank=True`、`default=""` | 无 | 设备系统版本 |
| `device_model` | `CharField(100)` | `blank=True`、`default=""` | 无 | 设备型号，如 iPhone14,2 |
| `device_model_name` | `CharField(100)` | `blank=True`、`default=""` | 无 | 设备型号名称，如 iPhone 14 Pro |
| `device_name` | `CharField(255)` | `blank=True`、`default=""` | 无 | 用户自定义设备名称 |
| `screen_size` | `CharField(50)` | `blank=True`、`default=""` | 无 | 屏幕尺寸（宽度×高度） |
| `screen_scale` | `FloatField` | `null=True`、`blank=True` | 无 | 屏幕缩放比例 |
| `time_zone` | `CharField(50)` | `blank=True`、`default=""` | 无 | 设备时区标识符 |
| `language_code` | `CharField(10)` | `blank=True`、`default=""` | 无 | 设备语言代码 |
| `region_code` | `CharField(10)` | `blank=True`、`default=""` | 无 | 设备地区代码 |
| `is_simulator` | `BooleanField` | `default=False` | 无 | 是否为模拟器 |
| `verified` | `BooleanField` | `default=False` | 无 | 设备是否已验证，默认未验证 |
| `first_seen` | `DateTimeField` | `auto_now_add=True` | 无 | 设备首次发现时间，自动赋值 |
| `last_seen` | `DateTimeField` | `auto_now=True` | 无 | 设备最后访问时间，每次保存自动更新 |

#### 元数据配置

- **唯一约束（需求）**：`(bundle_id, device_id)` 联合唯一，约束名建议 `uniq_bundle_device`，确保同一应用包下设备仅一条记录。
- **说明**：与历史 `(user, device_id)` 唯一方案不一致时，以产品选型与数据迁移为准；`user` 字段索引按需求文档列为「无」，若 ORM 默认创建外键索引，实现层可保留或显式关闭以与需求一致。

---

## 5.3 登录审计（LoginAudit）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `LoginAudit` |
| 数据库表名 | `accounts_loginaudit` |
| 模型说明 | 登录尝试审计。 |
| 核心功能 | 1. 失败登录 `user` 可空；2. 留存 claims。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `SET_NULL` 可空 | 无 | `related_name=login_audits` |
| `provider` | `CharField(32)` | `choices` password/email_otp/… | 无 | 登录渠道 |
| `outcome` | `CharField(16)` | `choices` success/failed | 普通索引（`db_index=True`） | 结果 |
| `ip_address` | `CharField(64)` | 可空 | 无 | IP |
| `user_agent` | `TextField` | 可空 | 无 | UA |
| `bundle_id` | `CharField(128)` | 可空 | 无 | 包名 |
| `device_id` | `CharField(128)` | 可空 | 无 | 设备 ID |
| `raw_claims` | `JSONField` | 可空 | 无 | 原始 claims |
| `request_id` | `CharField(64)` | 可空 | 无 | 请求 ID |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |

---

## 5.4 社交身份（SocialIdentity）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `SocialIdentity` |
| 数据库表名 | `accounts_socialidentity` |
| 模型说明 | Apple/Google 等与本地用户绑定。 |
| 核心功能 | 1. 包+渠道+provider_uid 唯一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 无 | `related_name=social_identities` |
| `provider` | `CharField(32)` | `choices` apple/google | 普通索引（`db_index=True`） | 渠道 |
| `provider_uid` | `CharField(255)` | NOT NULL | 普通索引（`db_index=True`） | 第三方用户 ID |
| `bundle_id` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 包名 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- **唯一约束**：`(bundle_id, provider, provider_uid)` → `uniq_social_identity_bundle_provider_uid`。

---

## 5.5 邮箱 OTP（EmailOTP）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `EmailOTP` |
| 数据库表名 | `accounts_emailotp` |
| 模型说明 | 邮箱验证码发放与校验（哈希存储）。 |
| 核心功能 | 1. 限流维度字段；2. 过期与锁定。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `otp_id` | `CharField(64)` | `unique` | 唯一索引 | OTP 业务 ID |
| `email` | `EmailField` | NOT NULL | 普通索引（`db_index=True`） | 邮箱 |
| `code_hash` | `CharField(64)` | NOT NULL | 普通索引（`db_index=True`） | 验证码哈希 |
| `expires_at` | `DateTimeField` | NOT NULL | 普通索引（`db_index=True`） | 过期时间 |
| `used_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 使用时间 |
| `attempts` | `PositiveIntegerField` | 默认 0 | 无 | 尝试次数 |
| `locked_until` | `DateTimeField` | 可空 | 无 | 锁定截止 |
| `provider_uid` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 关联身份 |
| `bundle_id` | `CharField(128)` | 可空 | 无 | 包名 |
| `device_id` | `CharField(128)` | 可空 | 无 | 设备 |
| `ip_address` | `CharField(64)` | 可空 | 无 | IP |
| `request_id` | `CharField(64)` | 可空 | 无 | 请求 ID |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |

#### 元数据配置

- 联合索引：`(email, expires_at)`。

---

## 5.6 短信 OTP（PhoneOTP）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `PhoneOTP` |
| 数据库表名 | `accounts_phoneotp` |
| 模型说明 | 短信验证码（结构与邮箱 OTP 对称）。 |
| 核心功能 | 1. `phone_number` 维度检索与过期。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `otp_id` | `CharField(64)` | `unique` | 唯一索引 | OTP 业务 ID |
| `phone_number` | `CharField(32)` | NOT NULL | 普通索引（`db_index=True`） | 手机号 |
| `code_hash` | `CharField(64)` | NOT NULL | 普通索引（`db_index=True`） | 验证码哈希 |
| `expires_at` | `DateTimeField` | NOT NULL | 普通索引（`db_index=True`） | 过期时间 |
| `used_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 使用时间 |
| `attempts` | `PositiveIntegerField` | 默认 0 | 无 | 尝试次数 |
| `locked_until` | `DateTimeField` | 可空 | 无 | 锁定截止 |
| `provider_uid` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 关联身份 |
| `bundle_id` | `CharField(128)` | 可空 | 无 | 包名 |
| `device_id` | `CharField(128)` | 可空 | 无 | 设备 |
| `ip_address` | `CharField(64)` | 可空 | 无 | IP |
| `request_id` | `CharField(64)` | 可空 | 无 | 请求 ID |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |

#### 元数据配置

- 联合索引：`(phone_number, expires_at)`。

---

## 5.7 账户销户（AccountDeactivation）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AccountDeactivation` |
| 数据库表名 | `accounts_accountdeactivation` |
| 模型说明 | 销户流水线主记录。 |
| 核心功能 | 1. 状态机；2. 冻结邮箱/手机副本。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 无 | `related_name=deactivations` |
| `state` | `CharField(32)` | `choices` 多状态，默认 requested | 普通索引（`db_index=True`） | 当前状态 |
| `requested_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 申请时间 |
| `scheduled_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 计划执行时间 |
| `processed_at` | `DateTimeField` | 可空 | 无 | 处理中时间 |
| `completed_at` | `DateTimeField` | 可空 | 无 | 完成时间 |
| `cancelled_at` | `DateTimeField` | 可空 | 无 | 取消时间 |
| `failed_at` | `DateTimeField` | 可空 | 无 | 失败时间 |
| `freeze_email` | `EmailField` | 可空 | 无 | 冻结邮箱快照 |
| `freeze_phone_number` | `CharField(32)` | 可空 | 无 | 冻结手机快照 |
| `error_message` | `TextField` | 可空 | 无 | 错误信息 |
| `request_id` | `CharField(64)` | 可空 | 无 | 请求 ID |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |

---

## 5.8 销户审计（AccountDeactivationAudit）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AccountDeactivationAudit` |
| 数据库表名 | `accounts_accountdeactivationaudit` |
| 模型说明 | 销户步骤审计。 |
| 核心功能 | 1. 一步一条；2. JSON 详情。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `deactivation` | `ForeignKey(AccountDeactivation)` | `CASCADE` | 无 | `related_name=audits` |
| `action` | `CharField(64)` | `choices` 冻结/匿名/清理OTP 等 | 普通索引（`db_index=True`） | 步骤动作 |
| `request_id` | `CharField(64)` | 可空 | 无 | 请求 ID |
| `details` | `JSONField` | 可空 | 无 | 步骤详情 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |

---

# 六、AI 配置与试用模块（ai_config）

## 6.1 场景模型绑定（AIScenarioModelBinding）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AIScenarioModelBinding` |
| 数据库表名 | `ai_config_aiscenariomodelbinding` |
| 模型说明 | 场景与目录模型多对多配置；每场景单一默认模型。 |
| 核心功能 | 1. `default_marker` 兼容 MySQL 唯一默认；2. `save()` 清理同场景其他默认。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `scenario` | `CharField(64)` | `choices=ScenarioKey` | 普通索引（`db_index=True`） | 场景标识 |
| `identity` | `CharField(16)` | `choices` model/agent，默认 model | 无 | 身份类型 |
| `model` | `ForeignKey(AIModelCatalog)` | `PROTECT` | 无 | `related_name=scenario_bindings` |
| `temperature` | `FloatField` | 默认 0.2 | 无 | 温度 |
| `max_tokens` | `IntegerField` | 默认 2048 | 无 | 最大输出 token |
| `position` | `IntegerField` | 默认 0 | 普通索引（`db_index=True`） | 排序 |
| `is_default` | `BooleanField` | 默认 False | 普通索引（`db_index=True`） | 是否默认 |
| `is_active` | `BooleanField` | 默认 True | 普通索引（`db_index=True`） | 是否启用 |
| `default_marker` | `CharField(80)` | 可空 `unique` | 唯一索引 | 默认占位唯一键 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- **唯一约束**：`(scenario, model)` → `uniq_scenario_model_binding`。
- 排序：`scenario`, `position`, `model__name`。

---

## 6.2 厂商 Key 配置（AIProviderKeyConfig）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AIProviderKeyConfig` |
| 数据库表名 | `ai_config_aiproviderkeyconfig` |
| 模型说明 | 厂商 API/搜索/工具连接配置。 |
| 核心功能 | 1. kind+company+name 唯一；2. 敏感 `key` 保护。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `kind` | `CharField(16)` | `choices` api/search/tool | 普通索引（`db_index=True`） | 配置种类 |
| `name` | `CharField(128)` | NOT NULL | 无 | 名称 |
| `company` | `CharField(64)` | NOT NULL | 无 | 厂商 |
| `key` | `CharField(512)` | 可空 | 无 | 密钥（须保护） |
| `request_url` | `CharField(512)` | NOT NULL | 无 | 请求 URL |
| `is_hidden` | `BooleanField` | 默认 False | 无 | 是否隐藏 |
| `is_using` | `BooleanField` | 默认 False | 无 | 是否使用中 |
| `capability_class` | `CharField(64)` | 可空 | 无 | 能力类 |
| `help` | `CharField(255)` | 可空 | 无 | 帮助文案 |
| `privacy_policy_url` | `CharField(512)` | 可空 | 无 | 隐私政策 |
| `source` | `CharField(16)` | `choices` system/custom | 无 | 来源 |
| `position` | `IntegerField` | 默认 0 | 无 | 排序 |
| `is_active` | `BooleanField` | 默认 True | 普通索引（`db_index=True`） | 是否启用 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- **唯一约束**：`(kind, company, name)` → `uniq_ai_provider_key_kind_company_name`。
- 排序：`kind`, `position`, `company`, `name`。

---

## 6.3 模型目录（AIModelCatalog）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AIModelCatalog` |
| 数据库表名 | `ai_config_aimodelcatalog` |
| 模型说明 | 可下发模型元数据与能力标签。 |
| 核心功能 | 1. `name` 全局唯一；2. `price_tier` 0–3 检查约束。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `name` | `CharField(128)` | `unique` | 唯一索引 | 模型 ID |
| `display_name` | `CharField(128)` | NOT NULL | 无 | 展示名 |
| `position` | `IntegerField` | 默认 0 | 普通索引（`db_index=True`） | 排序 |
| `company` | `CharField(64)` | NOT NULL | 无 | 厂商 |
| `is_hidden` | `BooleanField` | 默认 False | 无 | 是否隐藏 |
| `supports_search` | `BooleanField` | 默认 False | 无 | 联网搜索 |
| `supports_multimodal` | `BooleanField` | 默认 False | 无 | 多模态 |
| `supports_reasoning` | `BooleanField` | 默认 False | 无 | 推理 |
| `supports_tool_use` | `BooleanField` | 默认 False | 无 | 工具调用 |
| `supports_voice_gen` | `BooleanField` | 默认 False | 无 | 语音生成 |
| `supports_image_gen` | `BooleanField` | 默认 False | 无 | 图像生成 |
| `price_tier` | `PositiveSmallIntegerField` | 默认 0，CHECK 0–3 | 无 | 价格档位 |
| `supports_text` | `BooleanField` | 默认 True | 无 | 文本生成 |
| `reasoning_controllable` | `BooleanField` | 默认 False | 无 | 推理可控 |
| `source` | `CharField(16)` | `choices` system/custom | 无 | 来源 |
| `is_active` | `BooleanField` | 默认 True | 普通索引（`db_index=True`） | 是否启用 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- **检查约束**：`aimodelcatalog_price_tier_0_3`。
- 排序：`position`, `name`。

---

## 6.4 Bootstrap 配置（AIBootstrapProfile）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AIBootstrapProfile` |
| 数据库表名 | `ai_config_aibootstrapprofile` |
| 模型说明 | 客户端/服务启动下发参数聚合。 |
| 核心功能 | 1. `key` 唯一；2. 知识库与搜索等开关。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `key` | `CharField(32)` | `unique`，默认 default | 唯一索引 | 配置键 |
| `choose_embedding_model` | `CharField(128)` | 可空 | 无 | 嵌入模型 |
| `optimization_text_model` | `CharField(128)` | 可空 | 无 | 文本优化模型 |
| `optimization_visual_model` | `CharField(128)` | 可空 | 无 | 视觉优化模型 |
| `text_to_speech_model` | `CharField(128)` | 可空 | 无 | TTS 模型 |
| `use_knowledge` | `BooleanField` | 默认 True | 无 | 知识库 |
| `knowledge_count` | `IntegerField` | 默认 5 | 无 | 知识条数 |
| `knowledge_similarity` | `FloatField` | 默认 0.75 | 无 | 相似度阈值 |
| `use_search` | `BooleanField` | 默认 True | 无 | 搜索 |
| `bilingual_search` | `BooleanField` | 默认 False | 无 | 双语搜索 |
| `search_count` | `IntegerField` | 默认 3 | 无 | 搜索条数 |
| `use_map` | `BooleanField` | 默认 False | 无 | 地图工具 |
| `use_calendar` | `BooleanField` | 默认 False | 无 | 日历工具 |
| `use_weather` | `BooleanField` | 默认 False | 无 | 天气工具 |
| `use_canvas` | `BooleanField` | 默认 False | 无 | 画布工具 |
| `use_code` | `BooleanField` | 默认 False | 无 | 代码工具 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- 排序：`-updated_at`。

---

## 6.5 试用申请（TrialApplication）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `TrialApplication` |
| 数据库表名 | `ai_config_trialapplication` |
| 模型说明 | 用户试用资格一对一记录。 |
| 核心功能 | 1. `is_active_trial()` 判断；2. 状态与时间线。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `OneToOneField(User)` | `CASCADE` | 无 | `related_name=trial_application` |
| `status` | `CharField(16)` | `choices` none/pending/active/… | 普通索引（`db_index=True`） | 试用状态 |
| `grant_source` | `CharField(16)` | `choices` auto/manual/application | 无 | 授予来源 |
| `started_at` | `DateTimeField` | 可空 | 无 | 开始时间 |
| `expires_at` | `DateTimeField` | 可空 | 普通索引（`db_index=True`） | 过期时间 |
| `applied_at` | `DateTimeField` | 可空 | 无 | 申请时间 |
| `approved_at` | `DateTimeField` | 可空 | 无 | 通过时间 |
| `rejected_at` | `DateTimeField` | 可空 | 无 | 拒绝时间 |
| `note` | `CharField(255)` | 可空 | 无 | 备注 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- 排序：`-updated_at`。

---

## 6.6 试用策略（TrialModelPolicy）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `TrialModelPolicy` |
| 数据库表名 | `ai_config_trialmodelpolicy` |
| 模型说明 | 试用模型白名单策略头。 |
| 核心功能 | 1. `key` 唯一；2. 启用开关。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `key` | `CharField(32)` | `unique`，默认 default | 唯一索引 | 策略键 |
| `name` | `CharField(64)` | 默认文案 | 无 | 策略名称 |
| `description` | `CharField(255)` | 可空 | 无 | 描述 |
| `is_active` | `BooleanField` | 默认 True | 普通索引（`db_index=True`） | 是否启用 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- 排序：`-updated_at`。

---

## 6.7 试用策略条目（TrialModelPolicyItem）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `TrialModelPolicyItem` |
| 数据库表名 | `ai_config_trialmodelpolicyitem` |
| 模型说明 | 策略下按场景的模型条目。 |
| 核心功能 | 1. `(policy, scenario, model)` 唯一；2. `trial_default_marker` 每策略每场景单一默认。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `policy` | `ForeignKey(TrialModelPolicy)` | `CASCADE` | 无 | `related_name=items` |
| `scenario` | `CharField(64)` | `choices=ScenarioKey` | 无 | 场景 |
| `identity` | `CharField(16)` | 默认 model | 无 | 身份类型 |
| `model` | `ForeignKey(AIModelCatalog)` | `PROTECT` | 无 | `related_name=trial_policy_items` |
| `temperature` | `FloatField` | 默认 0.2 | 无 | 温度 |
| `max_tokens` | `IntegerField` | 默认 2048 | 无 | 最大 token |
| `position` | `IntegerField` | 默认 0 | 无 | 排序 |
| `is_default` | `BooleanField` | 默认 False | 普通索引（`db_index=True`） | 场景内默认 |
| `is_active` | `BooleanField` | 默认 True | 普通索引（`db_index=True`） | 是否启用 |
| `trial_default_marker` | `CharField(96)` | 可空 `unique` | 唯一索引 | 默认占位唯一键 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- **唯一约束**：`(policy, scenario, model)` → `uniq_trial_policy_scenario_model`。
- 排序：`position`, `scenario`, `model__name`。

---

# 七、对象存储模块（file_manager）

## 7.1 托管文件（ManagedFile）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ManagedFile` |
| 数据库表名 | `file_manager_managedfile` |
| 模型说明 | 用户文件元数据与 OSS 对象键。 |
| 核心功能 | 1. 业务维度挂载；2. `soft_delete()`。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 普通索引（`db_index=True`） | `related_name=managed_files` |
| `file_uuid` | `UUIDField` | `unique`，默认 uuid4 | 唯一索引 | 文件 UUID |
| `file_path` | `CharField(1024)` | 可空 | 无 | 逻辑路径 |
| `original_name` | `CharField(255)` | NOT NULL | 无 | 原始文件名 |
| `file_ext` | `CharField(32)` | 可空 | 无 | 扩展名 |
| `mime_type` | `CharField(128)` | 可空 | 无 | MIME |
| `file_size` | `BigIntegerField` | 默认 0 | 无 | 字节大小 |
| `file_md5` | `CharField(64)` | 可空 | 无 | MD5 |
| `is_public` | `BooleanField` | 默认 False | 普通索引（`db_index=True`） | 是否公开 |
| `business_type` | `CharField(64)` | 可空 | 普通索引（`db_index=True`） | 业务类型 |
| `business_id` | `CharField(64)` | 可空 | 普通索引（`db_index=True`） | 业务 ID |
| `object_key` | `CharField(1024)` | 可空 | 无 | OSS 对象键 |
| `storage_type` | `CharField(32)` | 默认 oss | 无 | 存储类型 |
| `is_deleted` | `BooleanField` | 默认 False | 普通索引（`db_index=True`） | 软删除 |
| `deleted_at` | `DateTimeField` | 可空 | 无 | 删除时间 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 更新时间 |

#### 元数据配置

- 联合索引：`(user, is_deleted, updated_at)`；`(user, business_type, business_id, is_deleted)`。
- 排序：`-created_at`, `-id`。
- 方法：`soft_delete()`。

---

# 八、后台 RBAC 与审计（backoffice）

## 8.1 后台角色（AdminRole）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminRole` |
| 数据库表名 | `backoffice_adminrole` |
| 模型说明 | 运营后台角色定义。 |
| 核心功能 | 1. name/code 唯一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `name` | `CharField(64)` | `unique` | 唯一索引 | 角色名称 |
| `code` | `CharField(64)` | `unique` | 唯一索引 | 角色编码 |
| `description` | `CharField(255)` | 可空 | 无 | 描述 |
| `is_active` | `BooleanField` | 默认 True | 普通索引（`db_index=True`） | 是否启用 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- 排序：`name`, `id`。

---

## 8.2 后台权限（AdminPermission）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminPermission` |
| 数据库表名 | `backoffice_adminpermission` |
| 模型说明 | 菜单/按钮/API 权限点。 |
| 核心功能 | 1. `code` 唯一；2. 树形 `parent_code`。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `name` | `CharField(128)` | NOT NULL | 无 | 权限名称 |
| `code` | `CharField(128)` | `unique` | 唯一索引 | 权限编码 |
| `permission_type` | `CharField(16)` | `choices` menu/button/api | 普通索引（`db_index=True`） | 类型 |
| `path` | `CharField(255)` | 可空 | 无 | 路径 |
| `method` | `CharField(16)` | 可空 | 无 | HTTP 方法 |
| `parent_code` | `CharField(128)` | 可空 | 普通索引（`db_index=True`） | 父编码 |
| `is_active` | `BooleanField` | 默认 True | 普通索引（`db_index=True`） | 是否启用 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |

#### 元数据配置

- 排序：`permission_type`, `code`, `id`。

---

## 8.3 角色权限关联（AdminRolePermission）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminRolePermission` |
| 数据库表名 | `backoffice_adminrolepermission` |
| 模型说明 | 角色与权限 M:N。 |
| 核心功能 | 1. 组合唯一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `role` | `ForeignKey(AdminRole)` | `CASCADE` | 无 | `related_name=role_permissions` |
| `permission` | `ForeignKey(AdminPermission)` | `CASCADE` | 无 | `related_name=permission_roles` |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |

#### 元数据配置

- **唯一约束**：`(role, permission)` → `uniq_admin_role_permission`。

---

## 8.4 用户角色关联（AdminUserRole）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminUserRole` |
| 数据库表名 | `backoffice_adminuserrole` |
| 模型说明 | 后台用户与角色 M:N。 |
| 核心功能 | 1. 组合唯一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 无 | `related_name=admin_user_roles` |
| `role` | `ForeignKey(AdminRole)` | `CASCADE` | 无 | `related_name=role_users` |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |

#### 元数据配置

- **唯一约束**：`(user, role)` → `uniq_admin_user_role`。

---

## 8.5 管理审计日志（AdminAuditLog）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminAuditLog` |
| 数据库表名 | `backoffice_adminauditlog` |
| 模型说明 | 后台 API 操作审计。 |
| 核心功能 | 1. 可选用户；2. 请求/响应 JSON。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `SET_NULL` 可空 | 无 | 操作人 |
| `action` | `CharField(128)` | NOT NULL | 普通索引（`db_index=True`） | 动作 |
| `resource_type` | `CharField(64)` | 可空 | 普通索引（`db_index=True`） | 资源类型 |
| `resource_id` | `CharField(64)` | 可空 | 无 | 资源 ID |
| `method` | `CharField(16)` | 可空 | 无 | HTTP 方法 |
| `path` | `CharField(255)` | 可空 | 普通索引（`db_index=True`） | 请求路径 |
| `status_code` | `IntegerField` | 默认 0 | 普通索引（`db_index=True`） | HTTP 状态码 |
| `request_id` | `CharField(64)` | 可空 | 普通索引（`db_index=True`） | 请求 ID |
| `ip_address` | `CharField(64)` | 可空 | 无 | IP |
| `user_agent` | `TextField` | 可空 | 无 | UA |
| `request_payload` | `JSONField` | 可空 | 无 | 请求体摘要 |
| `response_payload` | `JSONField` | 可空 | 无 | 响应体摘要 |
| `created_at` | `DateTimeField` | `auto_now_add` | 普通索引（`db_index=True`） | 创建时间 |

#### 元数据配置

- 排序：`-created_at`, `-id`。

---

## 8.6 权限种子标记（AdminPermissionPreset）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminPermissionPreset` |
| 数据库表名 | `backoffice_adminpermissionpreset` |
| 模型说明 | RBAC 种子幂等标记。 |
| 核心功能 | 1. `key` 唯一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `key` | `CharField(64)` | `unique` | 唯一索引 | 种子键 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |

---

# 九、聊天同步模块（chat_sync）

## 9.1 会话（ChatThread）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ChatThread` |
| 数据库表名 | `chat_sync_chatthread` |
| 模型说明 | 用户聊天线程，主键 UUID。 |
| 核心功能 | 1. 可选 `patient_id`；2. 同步 `server_updated_at`。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `UUIDField` | PRIMARY KEY，默认 uuid4 | 主键索引 | 线程 ID |
| `user` | `ForeignKey(User)` | `CASCADE` | 无 | `related_name=chat_threads` |
| `patient_id` | `UUIDField` | 可空 | 普通索引（`db_index=True`） | 客户端成员/档案 UUID |
| `title` | `CharField(255)` | 默认 New Chat | 无 | 标题 |
| `scenario` | `CharField(32)` | `choices` chat | 无 | 场景 |
| `is_deleted` | `BooleanField` | 默认 False | 普通索引（`db_index=True`） | 软删除 |
| `created_at` | `DateTimeField` | `auto_now_add` | 无 | 创建时间 |
| `updated_at` | `DateTimeField` | `auto_now` | 无 | 更新时间 |
| `server_updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 服务端同步时间 |

#### 元数据配置

- **唯一约束**：`(user, id)` → `uniq_chat_thread_user_thread`。
- 排序：`-updated_at`。

---

## 9.2 消息（ChatMessage）

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ChatMessage` |
| 数据库表名 | `chat_sync_chatmessage` |
| 模型说明 | 线程内消息与投递状态。 |
| 核心功能 | 1. 客户端/服务端消息 ID 唯一；2. 增量同步索引。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | `BigAutoField` | PRIMARY KEY | 主键索引 | 自增主键 |
| `user` | `ForeignKey(User)` | `CASCADE` | 无 | `related_name=chat_messages` |
| `thread` | `ForeignKey(ChatThread)` | `CASCADE` | 无 | `related_name=messages` |
| `role` | `CharField(16)` | `choices` system/user/assistant | 无 | 角色 |
| `kind` | `CharField(16)` | `choices` text/tool/card/system，默认 text | 无 | 消息种类 |
| `content` | `TextField` | 可空 | 无 | 正文 |
| `client_message_id` | `UUIDField` | NOT NULL | 普通索引（`db_index=True`） | 客户端消息 ID |
| `server_message_id` | `CharField(64)` | NOT NULL | 普通索引（`db_index=True`） | 服务端消息 ID |
| `delivery_state` | `CharField(16)` | `choices` pending/…，默认 sent | 无 | 投递状态 |
| `tombstone` | `BooleanField` | 默认 False | 普通索引（`db_index=True`） | 墓碑删除 |
| `metadata` | `JSONField` | `default=dict` | 无 | 扩展元数据 |
| `created_at` | `DateTimeField` | 业务写入 | 普通索引（`db_index=True`） | 消息时间 |
| `server_updated_at` | `DateTimeField` | `auto_now` | 普通索引（`db_index=True`） | 服务端更新时间 |

#### 元数据配置

- **唯一约束**：`(user, client_message_id)`；`(user, server_message_id)`。
- 索引：`idx_chat_msg_user_sync (user, server_updated_at, id)`；`idx_chat_msg_thread_created (thread, created_at, id)`。
- 排序：`created_at`, `id`。

---

# 十、模型关联关系总览

| 子模块 | 核心实体 | 主要关系 |
| --- | --- | --- |
| 成员与病历 | `Member`、`MedicalCase` | `Member`→`User`；`MedicalCase`→`Member`+`User` |
| 病历子表 | `Symptom`、`Visit`、`Surgery`、`FollowUp` | 均→`MedicalCase`、`Member`、`User` |
| 检查 | `ExaminationReport` | →`Member`；可选→`MedicalCase`（`medical_record`） |
| 体检 | `HealthExamReport` | →`Member` |
| 明细 | `MedExamDetail` | →`Member`；逻辑挂载主表 |
| 用药 | `PrescriptionBatch`、`Medication`、`MedicationTakenRecord` | 均含 `user`+`member`；批次可选 `medical_case` |
| 审计 | `ModelChangeLog` | →`User`，可选→`Member` |
| 指标 | `HealthMetricRecord` | →`User`；`profile_client_uid` |
| 账户 | `AccountProfile` 等 | 围绕 `User` |
| AI | 绑定/试用 | →`AIModelCatalog` 等 |
| 文件 | `ManagedFile` | →`User` |
| 后台 | RBAC | `AdminUserRole`、`AdminRolePermission` |
| 聊天 | `ChatThread`、`ChatMessage` | →`User`；消息→线程 |

---

# 十一、修订记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| V1.0 | 2026年04月 | 初稿（节选） |
| V2.0 | 2026年04月 | 全量对齐 ORM |
| V2.1 | 2026年04月 | **版式统一**：各模型采用「项目/详情」四行表 +「字段详细设计」五列表（字段名、数据类型、约束、索引、字段说明），并补充元数据配置（排序、唯一约束、联合索引等） |
| V2.2 | 2026年04月 | **`TrustedDevice` 需求升级**：扩充推送、版本、设备软硬件/本地化/验证字段；`bundle_id`/`device_id` 长度与非空；时间字段改为 `first_seen`/`last_seen`；唯一约束建议 `(bundle_id, device_id)` |
