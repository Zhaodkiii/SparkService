### Member

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Member` |
| 数据库表名 | `medical_member` |
| 模型说明 | 账号下的家庭就诊成员（本人与亲属），病历/检查/体检/用药等业务挂载主体。 |
| 核心功能 | 1. 维护成员人口学与过敏、慢病等安全信息；2. 标记与主账户关系及主档案优先展示；3. 与用户级联清理。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `name` | CharField(64) | NOT NULL | 无 | — |
| `gender` | CharField(16) | NOT NULL、default=Member.Gender.UNKNOWN、choices 枚举 | 无 | — |
| `relationship` | CharField(64) | NOT NULL、default='self' | 无 | — |
| `birth_date` | DateField | NULL、blank=True | 无 | — |
| `blood_type` | CharField(8) | NOT NULL、blank=True、default='' | 无 | — |
| `allergies` | JSONField | NOT NULL、blank=True、default=callable | 无 | — |
| `chronic_conditions` | JSONField | NOT NULL、blank=True、default=callable | 无 | — |
| `notes` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `avatar_url` | CharField(512) | NOT NULL、blank=True、default='' | 无 | — |
| `is_primary` | BooleanField | NOT NULL、default=False | 普通索引 | — |

#### 元数据配置

- 默认排序：`['-is_primary', '-updated_at', '-id']`

---

### MedicalCase

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `MedicalCase` |
| 数据库表名 | `medical_medicalcase` |
| 模型说明 | 门诊/住院等病历叙事聚合根；主档瘦身，细节在子表。 |
| 核心功能 | 1. 关联成员与用户；2. 状态机草稿/已提交/已归档；3. 承载类型、医院与诊断摘要；4. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `record_type` | CharField(32) | NOT NULL、default='custom' | 普通索引 | — |
| `status` | PositiveSmallIntegerField | NOT NULL、default=MedicalCase.Status.DRAFT、choices 枚举 | 普通索引 | — |
| `title` | CharField(255) | NOT NULL、blank=True、default='' | 无 | — |
| `hospital_name` | CharField(255) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `age_at_visit` | PositiveSmallIntegerField | NULL、blank=True | 无 | — |
| `diagnosis_summary` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `extra` | JSONField | NOT NULL、blank=True、default=callable | 无 | — |

#### 元数据配置

- 默认排序：`['-created_at', '-updated_at', '-id']`
- 联合索引 `(member, is_deleted, created_at)`
- 联合索引 `(member, record_type, is_deleted, created_at)`
- 联合索引 `(member, status, is_deleted, created_at)`
- 联合索引 `(hospital_name)`

---

### Symptom

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Symptom` |
| 数据库表名 | `medical_symptom` |
| 模型说明 | 病历下症状条目，支持时长与部位。 |
| 核心功能 | 1. 关联病历与成员；2. 结构化持续时间；3. 按部位检索；4. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `medical_case` | ForeignKey(MedicalCase) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `name` | CharField(128) | NOT NULL | 无 | — |
| `code` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `severity` | CharField(32) | NOT NULL、blank=True、default='' | 无 | — |
| `started_at` | DateTimeField | NULL、blank=True | 无 | — |
| `duration_value` | PositiveIntegerField | NULL、blank=True | 无 | — |
| `duration_unit` | CharField(16) | NOT NULL、blank=True、default='' | 无 | — |
| `body_part` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `notes` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `extra` | JSONField | NOT NULL、blank=True、default=callable | 无 | — |

#### 元数据配置

- 默认排序：`['-created_at', '-updated_at', '-id']`
- 联合索引 `(medical_case, created_at)`
- 联合索引 `(member, medical_case, is_deleted, created_at)`
- 联合索引 `(body_part)`

---

### Visit

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Visit` |
| 数据库表名 | `medical_visit` |
| 模型说明 | 病历下就诊节点（门诊/急诊等）。 |
| 核心功能 | 1. 时间轴与科室医生；2. 外部系统幂等 ID；3. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `medical_case` | ForeignKey(MedicalCase) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `visit_type` | CharField(32) | NOT NULL、default='custom' | 无 | — |
| `visited_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `department` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `doctor_name` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `visit_no` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `source_system_id` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `notes` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `extra` | JSONField | NOT NULL、blank=True、default=callable | 无 | — |

#### 元数据配置

- 默认排序：`['-visited_at', '-updated_at', '-id']`
- 联合索引 `(medical_case, visited_at)`
- 联合索引 `(member, medical_case, is_deleted, visited_at)`
- 联合索引 `(source_system_id)`

---

### Surgery

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Surgery` |
| 数据库表名 | `medical_surgery` |
| 模型说明 | 病历下手术/操作记录，含质控字段。 |
| 核心功能 | 1. 手术时间与术者麻醉；2. 切口等级与 ASA；3. 外部幂等 ID；4. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `medical_case` | ForeignKey(MedicalCase) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `procedure_name` | CharField(255) | NOT NULL | 无 | — |
| `procedure_code` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `site` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `performed_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `surgeon` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `anesthesia_type` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `incision_level` | CharField(8) | NOT NULL、blank=True、default='' | 无 | — |
| `asa_class` | CharField(8) | NOT NULL、blank=True、default='' | 无 | — |
| `source_system_id` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `notes` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `extra` | JSONField | NOT NULL、blank=True、default=callable | 无 | — |

#### 元数据配置

- 默认排序：`['-performed_at', '-updated_at', '-id']`
- 联合索引 `(medical_case, performed_at)`
- 联合索引 `(member, medical_case, is_deleted, performed_at)`
- 联合索引 `(source_system_id)`

---

### FollowUp

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `FollowUp` |
| 数据库表名 | `medical_followup` |
| 模型说明 | 病历下随访计划与执行。 |
| 核心功能 | 1. 计划/完成时间与状态；2. 方式与结果摘要；3. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `medical_case` | ForeignKey(MedicalCase) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `planned_at` | DateTimeField | NULL、blank=True | 无 | — |
| `completed_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `status` | CharField(20) | NOT NULL、default='initial' | 普通索引 | — |
| `method` | CharField(32) | NOT NULL、blank=True、default='' | 无 | — |
| `outcome` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `next_action` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `extra` | JSONField | NOT NULL、blank=True、default=callable | 无 | — |

#### 元数据配置

- 默认排序：`['-completed_at', '-updated_at', '-id']`
- 联合索引 `(medical_case, status, completed_at)`
- 联合索引 `(member, medical_case, is_deleted, completed_at)`

---

### ExaminationReport

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ExaminationReport` |
| 数据库表名 | `medical_examination_report` |
| 模型说明 | 临床检查/影像/病理等报告主表，可选归入病历。 |
| 核心功能 | 1. 成员必填、病历可选；2. OCR 与状态；3. 双时间轴；4. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `medical_record` | ForeignKey(MedicalCase) | NULL、blank=True、on_delete=SET_NULL | 外键索引 | — |
| `category` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `sub_category` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `item_name` | CharField(255) | NOT NULL | 无 | — |
| `performed_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `reported_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `organization_name` | CharField(255) | NULL、blank=True、default='' | 无 | — |
| `department_name` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `doctor_name` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `findings` | TextField | NULL、blank=True | 无 | — |
| `impression` | TextField | NULL、blank=True | 无 | — |
| `source` | PositiveSmallIntegerField | NOT NULL、default=ExaminationReport.Source.MANUAL、choices 枚举 | 无 | — |
| `raw_ocr` | JSONField | NULL、blank=True | 无 | — |
| `status` | PositiveSmallIntegerField | NOT NULL、default=ExaminationReport.Status.DRAFT、choices 枚举 | 普通索引 | — |
| `extra` | JSONField | NULL、blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['-reported_at', '-updated_at', '-id']`
- 联合索引 `(member, status, is_deleted)`
- 联合索引 `(member, performed_at, is_deleted)`
- 联合索引 `(member, reported_at, is_deleted)`

---

### HealthExamReport

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `HealthExamReport` |
| 数据库表名 | `medical_health_exam_report` |
| 模型说明 | 单次体检报告主表，明细见 MedExamDetail。 |
| 核心功能 | 1. 机构与报告号；2. 体检类型与来源枚举；3. OCR；4. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `institution_name` | CharField(255) | NOT NULL、blank=True、default='' | 无 | — |
| `report_no` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `exam_date` | DateField | NULL、blank=True | 普通索引 | — |
| `exam_type` | PositiveSmallIntegerField | NOT NULL、default=HealthExamReport.ExamType.ROUTINE、choices 枚举 | 无 | — |
| `summary` | TextField | NULL、blank=True | 无 | — |
| `source` | PositiveSmallIntegerField | NOT NULL、default=HealthExamReport.Source.MANUAL、choices 枚举 | 无 | — |
| `raw_ocr` | JSONField | NULL、blank=True | 无 | — |
| `status` | PositiveSmallIntegerField | NOT NULL、default=HealthExamReport.Status.DRAFT、choices 枚举 | 普通索引 | — |
| `extra` | JSONField | NULL、blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['-exam_date', '-updated_at', '-id']`
- 联合索引 `(member, exam_date, is_deleted)`
- 联合索引 `(member, status, is_deleted)`

---

### MedExamDetail

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `MedExamDetail` |
| 数据库表名 | `medical_med_exam_detail` |
| 模型说明 | 体检与临床检查共用的行级医技结果；多态挂载父主键。 |
| 核心功能 | 1. business_type + business_id；2. 成员强绑定；3. 默认管理器不过滤 is_deleted，业务层需处理；4. 无 deleted_at。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `business_type` | CharField(32) | NOT NULL、choices 枚举 | 普通索引 | — |
| `business_id` | PositiveBigIntegerField | NOT NULL | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `category` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `sub_category` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `item_name` | CharField(255) | NOT NULL | 无 | — |
| `item_code` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `result_value` | CharField(255) | NOT NULL、blank=True、default='' | 无 | — |
| `unit` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `reference_range` | CharField(255) | NOT NULL、blank=True、default='' | 无 | — |
| `flag` | CharField(16) | NOT NULL、blank=True、default='' | 无 | — |
| `result_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `modality` | CharField(32) | NOT NULL、blank=True、default='' | 无 | — |
| `body_part` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `diagnosis` | TextField | NULL、blank=True | 无 | — |
| `extra` | JSONField | NULL、blank=True | 无 | — |
| `sort_order` | PositiveIntegerField | NOT NULL、default=0 | 无 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |

#### 元数据配置

- 默认排序：`['sort_order', '-updated_at', '-id']`
- 联合索引 `(business_type, business_id, is_deleted)`
- 联合索引 `(member, is_deleted)`
- 联合索引 `(category, sub_category, is_deleted)`
- 联合索引 `(business_type, business_id, sort_order)`

---

### PrescriptionBatch

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `PrescriptionBatch` |
| 数据库表名 | `medical_prescription_batch` |
| 模型说明 | 处方或用药方案批次头。 |
| 核心功能 | 1. 关联成员与可选病历；2. clean/save 校验用户与成员一致；3. batch_no 空串入库 NULL；4. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | 所属就诊人 ID |
| `medical_case` | ForeignKey(MedicalCase) | NULL、blank=True、on_delete=SET_NULL | 外键索引 | 可选来源病例 ID |
| `prescriber_name` | CharField(128) | NOT NULL、blank=True、default='' | 无 | 开方医生 |
| `institution_name` | CharField(255) | NOT NULL、blank=True、default='' | 无 | 开方机构名称 |
| `prescribed_at` | DateTimeField | NULL、blank=True | 普通索引 | 开方/方案起始时间 |
| `diagnosis` | TextField | NOT NULL、blank=True、default='' | 无 | 诊断或适应症摘要 |
| `batch_no` | CharField(128) | NULL、blank=True、default=None | 无 | 业务批次号/处方号；不同病例可重复，未填时存库为 NULL |
| `status` | CharField(20) | NOT NULL、default=PrescriptionBatch.Status.ACTIVE、choices 枚举 | 普通索引 | — |
| `auditor_name` | CharField(128) | NOT NULL、blank=True、default='' | 无 | 审核人姓名 |
| `audited_at` | DateTimeField | NULL、blank=True | 无 | 审核时间 |
| `extra` | JSONField | NOT NULL、blank=True、default=callable | 无 | 扩展字段 |

#### 元数据配置

- 默认排序：`['-prescribed_at', '-updated_at', '-id']`
- 联合索引 `(user, member, is_deleted, prescribed_at)`
- 联合索引 `(medical_case)`
- 联合索引 `(batch_no)`

---

### Medication

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `Medication` |
| 数据库表名 | `medical_medication` |
| 模型说明 | 批次下药品行与提醒规则。 |
| 核心功能 | 1. 用法用量与频次；2. 与批次成员归属校验；3. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | 所属就诊人 ID |
| `batch` | ForeignKey(PrescriptionBatch) | NOT NULL、on_delete=CASCADE | 外键索引 | 所属处方批次 ID |
| `generic_name` | CharField(255) | NOT NULL、blank=True、default='' | 无 | 通用名 |
| `brand_name` | CharField(255) | NOT NULL、blank=True、default='' | 无 | 品牌名 |
| `drug_name` | CharField(255) | NOT NULL | 无 | 药品显示名 |
| `dosage_form` | CharField(64) | NOT NULL、blank=True、default='' | 无 | 剂型 |
| `strength` | CharField(128) | NOT NULL、blank=True、default='' | 无 | 规格 |
| `route` | CharField(64) | NOT NULL、blank=True、default='' | 无 | 给药途径 |
| `dose_per_time` | CharField(64) | NOT NULL、blank=True、default='' | 无 | 单次剂量文本 |
| `dose_value` | DecimalField(10,3) | NULL、blank=True | 无 | 单次剂量数值 |
| `dose_unit` | CharField(32) | NOT NULL、blank=True、default='' | 无 | 单次剂量单位 |
| `frequency_code` | CharField(64) | NOT NULL、blank=True、default='' | 无 | 频次编码 |
| `period` | CharField(16) | NOT NULL、blank=True、default='' | 无 | 频次周期 |
| `times_per_period` | PositiveSmallIntegerField | NULL、blank=True | 无 | 每周期次数 |
| `frequency_text` | CharField(255) | NOT NULL、blank=True、default='' | 无 | 频次展示文案 |
| `duration_days` | PositiveIntegerField | NULL、blank=True | 无 | 疗程天数 |
| `instructions` | TextField | NOT NULL、blank=True、default='' | 无 | 用药说明 |
| `reminder_enabled` | BooleanField | NOT NULL、default=True | 无 | 是否启用提醒 |
| `reminder_times` | JSONField | NOT NULL、blank=True、default=callable | 无 | 提醒时间点列表 |
| `sort_order` | PositiveIntegerField | NOT NULL、default=0 | 无 | 批次内排序 |
| `extra` | JSONField | NOT NULL、blank=True、default=callable | 无 | 扩展字段 |

#### 元数据配置

- 默认排序：`['sort_order', '-updated_at', '-id']`
- 联合索引 `(batch, sort_order)`
- 联合索引 `(user, member, is_deleted, created_at)`

---

### MedicationTakenRecord

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `MedicationTakenRecord` |
| 数据库表名 | `medical_medication_taken_record` |
| 模型说明 | 单次应服/已服/漏服打卡。 |
| 核心功能 | 1. 依从性统计；2. 唯一约束防重复计划；3. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `member` | ForeignKey(Member) | NOT NULL、on_delete=CASCADE | 外键索引 | 所属就诊人 ID |
| `medication` | ForeignKey(Medication) | NOT NULL、on_delete=CASCADE | 外键索引 | 对应药品行 ID |
| `scheduled_at` | DateTimeField | NOT NULL | 普通索引 | 计划服药时间 |
| `taken_at` | DateTimeField | NULL、blank=True | 无 | 实际服药时间 |
| `status` | CharField(20) | NOT NULL、default=MedicationTakenRecord.Status.SCHEDULED、choices 枚举 | 普通索引 | — |
| `dose_sequence` | PositiveSmallIntegerField | NOT NULL、default=1 | 无 | 当日第几次 |
| `actual_dose` | CharField(64) | NOT NULL、blank=True、default='' | 无 | 实际服用剂量文本 |
| `timezone` | CharField(64) | NOT NULL、blank=True、default='UTC' | 普通索引 | 打卡时区 |
| `notes` | TextField | NOT NULL、blank=True、default='' | 无 | 备注 |
| `extra` | JSONField | NOT NULL、blank=True、default=callable | 无 | 扩展字段 |

#### 元数据配置

- 默认排序：`['-scheduled_at', '-updated_at', '-id']`
- 联合索引 `(medication, scheduled_at, status)`
- 联合索引 `(user, member, scheduled_at, status)`
- 唯一约束 `(medication, scheduled_at, dose_sequence)` → `uniq_medication_schedule_sequence`

---

### ModelChangeLog

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ModelChangeLog` |
| 数据库表名 | `medical_model_change_log` |
| 模型说明 | 医疗域通用变更审计（Who/When/What）。 |
| 核心功能 | 1. 实体类型与主键；2. 状态迁移与字段 diff；3. 追踪 trace_id。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `member` | ForeignKey(Member) | NULL、blank=True、on_delete=SET_NULL | 外键索引 | — |
| `entity` | CharField(64) | NOT NULL | 普通索引 | — |
| `entity_id` | PositiveBigIntegerField | NOT NULL | 普通索引 | — |
| `action` | CharField(32) | NOT NULL | 普通索引 | — |
| `from_status` | CharField(32) | NOT NULL、blank=True、default='' | 无 | — |
| `to_status` | CharField(32) | NOT NULL、blank=True、default='' | 无 | — |
| `changed_fields` | JSONField | NOT NULL、blank=True、default=callable | 无 | — |
| `trace_id` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `operator` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |

#### 元数据配置

- 默认排序：`['-created_at', '-id']`

---

### HealthMetricRecord

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `HealthMetricRecord` |
| 数据库表名 | `medical_healthmetricrecord` |
| 模型说明 | 健康指标时间序列；按 profile_client_uid 归档，不外键 Member。 |
| 核心功能 | 1. 与用户绑定；2. 指标类型与采样时刻；3. 软删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |
| `profile_client_uid` | UUIDField | NOT NULL | 普通索引 | — |
| `metric_type` | CharField(64) | NOT NULL | 普通索引 | — |
| `value` | FloatField | NOT NULL、default=0 | 无 | — |
| `unit` | CharField(32) | NOT NULL、default='' | 无 | — |
| `recorded_at` | DateTimeField | NOT NULL | 普通索引 | — |
| `note` | TextField | NOT NULL、blank=True、default='' | 无 | — |

#### 元数据配置

- 默认排序：`['-recorded_at', '-updated_at', '-id']`

---

### AccountProfile

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AccountProfile` |
| 数据库表名 | `accounts_accountprofile` |
| 模型说明 | Django User 一对一业务扩展（如手机号）。 |
| 核心功能 | 1. 资料与 User 同步生命周期；2. 轻量扩展字段。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、UNIQUE、on_delete=CASCADE | 唯一索引 | — |
| `phone_number` | CharField(32) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 无额外表级索引/约束（或仅字段级索引，见上表）

---

### TrustedDevice

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `TrustedDevice` |
| 数据库表名 | `accounts_trusteddevice` |
| 模型说明 | 用户可信设备与包名，用于登录信任等。 |
| 核心功能 | 1. 用户+设备唯一；2. 撤销标记；3. 最后在线时间。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `device_id` | CharField(128) | NOT NULL | 普通索引 | — |
| `bundle_id` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `nickname` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `request_id` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `is_revoked` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |
| `last_seen_at` | DateTimeField | NOT NULL、default=callable | 无 | — |

#### 元数据配置

- 唯一约束 `(user, device_id)` → `uniq_trusted_device_per_user`

---

### LoginAudit

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `LoginAudit` |
| 数据库表名 | `accounts_loginaudit` |
| 模型说明 | 登录尝试审计（成功/失败）。 |
| 核心功能 | 1. 渠道与结果；2. IP/UA/包名/设备；3. 失败时 user 可空。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NULL、blank=True、on_delete=SET_NULL | 外键索引 | — |
| `provider` | CharField(32) | NOT NULL、choices 枚举 | 无 | — |
| `outcome` | CharField(16) | NOT NULL、choices 枚举 | 普通索引 | — |
| `ip_address` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `user_agent` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `bundle_id` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `device_id` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `raw_claims` | JSONField | NULL、blank=True | 无 | — |
| `request_id` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |

#### 元数据配置

- 无额外表级索引/约束（或仅字段级索引，见上表）

---

### SocialIdentity

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `SocialIdentity` |
| 数据库表名 | `accounts_socialidentity` |
| 模型说明 | 第三方（Apple/Google）身份绑定。 |
| 核心功能 | 1. 包名+渠道+provider_uid 唯一；2. 与用户多对一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `provider` | CharField(32) | NOT NULL、choices 枚举 | 普通索引 | — |
| `provider_uid` | CharField(255) | NOT NULL | 普通索引 | — |
| `bundle_id` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 唯一约束 `(bundle_id, provider, provider_uid)` → `uniq_social_identity_bundle_provider_uid`

---

### EmailOTP

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `EmailOTP` |
| 数据库表名 | `accounts_emailotp` |
| 模型说明 | 邮箱 OTP 发放与校验（哈希存储）。 |
| 核心功能 | 1. otp_id 唯一；2. 过期与锁定；3. 风控维度字段。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `otp_id` | CharField(64) | NOT NULL、UNIQUE | 唯一索引 | — |
| `email` | CharField(254) | NOT NULL | 普通索引 | — |
| `code_hash` | CharField(64) | NOT NULL | 普通索引 | — |
| `expires_at` | DateTimeField | NOT NULL | 普通索引 | — |
| `used_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `attempts` | PositiveIntegerField | NOT NULL、default=0 | 无 | — |
| `locked_until` | DateTimeField | NULL、blank=True | 无 | — |
| `provider_uid` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `bundle_id` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `device_id` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `ip_address` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `request_id` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 联合索引 `(email, expires_at)`

---

### PhoneOTP

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `PhoneOTP` |
| 数据库表名 | `accounts_phoneotp` |
| 模型说明 | 短信 OTP，与邮箱 OTP 字段对称。 |
| 核心功能 | 1. otp_id 唯一；2. 过期与锁定；3. 风控维度字段。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `otp_id` | CharField(64) | NOT NULL、UNIQUE | 唯一索引 | — |
| `phone_number` | CharField(32) | NOT NULL | 普通索引 | — |
| `code_hash` | CharField(64) | NOT NULL | 普通索引 | — |
| `expires_at` | DateTimeField | NOT NULL | 普通索引 | — |
| `used_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `attempts` | PositiveIntegerField | NOT NULL、default=0 | 无 | — |
| `locked_until` | DateTimeField | NULL、blank=True | 无 | — |
| `provider_uid` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `bundle_id` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `device_id` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `ip_address` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `request_id` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 联合索引 `(phone_number, expires_at)`

---

### AccountDeactivation

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AccountDeactivation` |
| 数据库表名 | `accounts_accountdeactivation` |
| 模型说明 | 销户流水线主记录。 |
| 核心功能 | 1. 状态机；2. 冻结邮箱/手机副本；3. 时间戳追踪。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `state` | CharField(32) | NOT NULL、default=AccountDeactivation.DeactivationState.REQUESTED、choices 枚举 | 普通索引 | — |
| `requested_at` | DateTimeField | blank=True | 普通索引 | — |
| `scheduled_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `processed_at` | DateTimeField | NULL、blank=True | 无 | — |
| `completed_at` | DateTimeField | NULL、blank=True | 无 | — |
| `cancelled_at` | DateTimeField | NULL、blank=True | 无 | — |
| `failed_at` | DateTimeField | NULL、blank=True | 无 | — |
| `freeze_email` | CharField(254) | NOT NULL、blank=True、default='' | 无 | — |
| `freeze_phone_number` | CharField(32) | NOT NULL、blank=True、default='' | 无 | — |
| `error_message` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `request_id` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 无额外表级索引/约束（或仅字段级索引，见上表）

---

### AccountDeactivationAudit

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AccountDeactivationAudit` |
| 数据库表名 | `accounts_accountdeactivationaudit` |
| 模型说明 | 销户步骤审计。 |
| 核心功能 | 1. 一步一条；2. JSON details。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `deactivation` | ForeignKey(AccountDeactivation) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `action` | CharField(64) | NOT NULL、choices 枚举 | 普通索引 | — |
| `request_id` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `details` | JSONField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 无额外表级索引/约束（或仅字段级索引，见上表）

---

### AIScenarioModelBinding

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AIScenarioModelBinding` |
| 数据库表名 | `ai_config_aiscenariomodelbinding` |
| 模型说明 | 场景与目录模型的绑定及默认模型。 |
| 核心功能 | 1. 同场景唯一默认（default_marker）；2. save 清理其他默认。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `scenario` | CharField(64) | NOT NULL、choices 枚举 | 普通索引 | — |
| `identity` | CharField(16) | NOT NULL、default=IdentityKind.MODEL、choices 枚举 | 无 | — |
| `model` | ForeignKey(AIModelCatalog) | NOT NULL、on_delete=PROTECT | 外键索引 | — |
| `temperature` | FloatField | NOT NULL、default=0.2 | 无 | — |
| `max_tokens` | IntegerField | NOT NULL、default=2048 | 无 | — |
| `position` | IntegerField | NOT NULL、default=0 | 普通索引 | — |
| `is_default` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `is_active` | BooleanField | NOT NULL、default=True | 普通索引 | — |
| `default_marker` | CharField(80) | NULL、blank=True、UNIQUE | 唯一索引 | Set to '<scenario>:default' when is_default; NULL otherwise. Enforces one default per scenario on MySQL. |
| `updated_at` | DateTimeField | blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['scenario', 'position', 'model__name']`
- 唯一约束 `(scenario, model)` → `uniq_scenario_model_binding`

---

### AIProviderKeyConfig

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AIProviderKeyConfig` |
| 数据库表名 | `ai_config_aiproviderkeyconfig` |
| 模型说明 | 厂商/工具 Key 与请求地址配置。 |
| 核心功能 | 1. kind+company+name 唯一；2. 敏感 key 字段保护。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `kind` | CharField(16) | NOT NULL、choices 枚举 | 普通索引 | — |
| `name` | CharField(128) | NOT NULL | 无 | — |
| `company` | CharField(64) | NOT NULL | 无 | — |
| `key` | CharField(512) | NOT NULL、blank=True、default='' | 无 | — |
| `request_url` | CharField(512) | NOT NULL | 无 | — |
| `is_hidden` | BooleanField | NOT NULL、default=False | 无 | — |
| `is_using` | BooleanField | NOT NULL、default=False | 无 | — |
| `capability_class` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `help` | CharField(255) | NOT NULL、blank=True、default='' | 无 | — |
| `privacy_policy_url` | CharField(512) | NOT NULL、blank=True、default='' | 无 | — |
| `source` | CharField(16) | NOT NULL、default=AIProviderKeyConfig.Source.SYSTEM、choices 枚举 | 无 | — |
| `position` | IntegerField | NOT NULL、default=0 | 无 | — |
| `is_active` | BooleanField | NOT NULL、default=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['kind', 'position', 'company', 'name']`
- 唯一约束 `(kind, company, name)` → `uniq_ai_provider_key_kind_company_name`

---

### AIModelCatalog

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AIModelCatalog` |
| 数据库表名 | `ai_config_aimodelcatalog` |
| 模型说明 | 可被选用的模型目录及能力标签。 |
| 核心功能 | 1. name 唯一；2. price_tier 0–3 检查约束。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `name` | CharField(128) | NOT NULL、UNIQUE | 唯一索引 | — |
| `display_name` | CharField(128) | NOT NULL | 无 | — |
| `position` | IntegerField | NOT NULL、default=0 | 普通索引 | — |
| `company` | CharField(64) | NOT NULL | 无 | — |
| `is_hidden` | BooleanField | NOT NULL、default=False | 无 | — |
| `supports_search` | BooleanField | NOT NULL、default=False | 无 | — |
| `supports_multimodal` | BooleanField | NOT NULL、default=False | 无 | — |
| `supports_reasoning` | BooleanField | NOT NULL、default=False | 无 | — |
| `supports_tool_use` | BooleanField | NOT NULL、default=False | 无 | — |
| `supports_voice_gen` | BooleanField | NOT NULL、default=False | 无 | — |
| `supports_image_gen` | BooleanField | NOT NULL、default=False | 无 | — |
| `price_tier` | PositiveSmallIntegerField | NOT NULL、default=0 | 无 | — |
| `supports_text` | BooleanField | NOT NULL、default=True | 无 | — |
| `reasoning_controllable` | BooleanField | NOT NULL、default=False | 无 | — |
| `source` | CharField(16) | NOT NULL、default=AIModelCatalog.Source.SYSTEM、choices 枚举 | 无 | — |
| `is_active` | BooleanField | NOT NULL、default=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['position', 'name']`
- 检查约束 `aimodelcatalog_price_tier_0_3`

---

### AIBootstrapProfile

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AIBootstrapProfile` |
| 数据库表名 | `ai_config_aibootstrapprofile` |
| 模型说明 | 客户端 Bootstrap 默认模型与功能开关。 |
| 核心功能 | 1. key 唯一；2. 知识库/搜索等总开关。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `key` | CharField(32) | NOT NULL、UNIQUE、default='default' | 唯一索引 | — |
| `choose_embedding_model` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `optimization_text_model` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `optimization_visual_model` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `text_to_speech_model` | CharField(128) | NOT NULL、blank=True、default='' | 无 | — |
| `use_knowledge` | BooleanField | NOT NULL、default=True | 无 | — |
| `knowledge_count` | IntegerField | NOT NULL、default=5 | 无 | — |
| `knowledge_similarity` | FloatField | NOT NULL、default=0.75 | 无 | — |
| `use_search` | BooleanField | NOT NULL、default=True | 无 | — |
| `bilingual_search` | BooleanField | NOT NULL、default=False | 无 | — |
| `search_count` | IntegerField | NOT NULL、default=3 | 无 | — |
| `use_map` | BooleanField | NOT NULL、default=False | 无 | — |
| `use_calendar` | BooleanField | NOT NULL、default=False | 无 | — |
| `use_weather` | BooleanField | NOT NULL、default=False | 无 | — |
| `use_canvas` | BooleanField | NOT NULL、default=False | 无 | — |
| `use_code` | BooleanField | NOT NULL、default=False | 无 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['-updated_at']`

---

### TrialApplication

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `TrialApplication` |
| 数据库表名 | `ai_config_trialapplication` |
| 模型说明 | 用户试用资格一对一记录。 |
| 核心功能 | 1. 状态与授权来源；2. is_active_trial() 判断。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、UNIQUE、on_delete=CASCADE | 唯一索引 | — |
| `status` | CharField(16) | NOT NULL、default=TrialApplication.Status.NONE、choices 枚举 | 普通索引 | — |
| `grant_source` | CharField(16) | NOT NULL、default=TrialApplication.GrantSource.AUTO、choices 枚举 | 无 | — |
| `started_at` | DateTimeField | NULL、blank=True | 无 | — |
| `expires_at` | DateTimeField | NULL、blank=True | 普通索引 | — |
| `applied_at` | DateTimeField | NULL、blank=True | 无 | — |
| `approved_at` | DateTimeField | NULL、blank=True | 无 | — |
| `rejected_at` | DateTimeField | NULL、blank=True | 无 | — |
| `note` | CharField(255) | NOT NULL、blank=True、default='' | 无 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['-updated_at']`

---

### TrialModelPolicy

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `TrialModelPolicy` |
| 数据库表名 | `ai_config_trialmodelpolicy` |
| 模型说明 | 试用模型策略头。 |
| 核心功能 | 1. key 唯一；2. 关联多条 TrialModelPolicyItem。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `key` | CharField(32) | NOT NULL、UNIQUE、default='default' | 唯一索引 | — |
| `name` | CharField(64) | NOT NULL、default='Default Trial Policy' | 无 | — |
| `description` | CharField(255) | NOT NULL、blank=True、default='' | 无 | — |
| `is_active` | BooleanField | NOT NULL、default=True | 普通索引 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['-updated_at']`

---

### TrialModelPolicyItem

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `TrialModelPolicyItem` |
| 数据库表名 | `ai_config_trialmodelpolicyitem` |
| 模型说明 | 策略下某场景的试用模型绑定。 |
| 核心功能 | 1. policy+scenario+model 唯一；2. 每策略每场景单一默认。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `policy` | ForeignKey(TrialModelPolicy) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `scenario` | CharField(64) | NOT NULL、choices 枚举 | 无 | — |
| `identity` | CharField(16) | NOT NULL、default=IdentityKind.MODEL、choices 枚举 | 无 | — |
| `model` | ForeignKey(AIModelCatalog) | NOT NULL、on_delete=PROTECT | 外键索引 | — |
| `temperature` | FloatField | NOT NULL、default=0.2 | 无 | — |
| `max_tokens` | IntegerField | NOT NULL、default=2048 | 无 | — |
| `position` | IntegerField | NOT NULL、default=0 | 无 | — |
| `is_default` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `is_active` | BooleanField | NOT NULL、default=True | 普通索引 | — |
| `trial_default_marker` | CharField(96) | NULL、blank=True、UNIQUE | 唯一索引 | Set to 'p<policy_id>_s<scenario>:default' when is_default; NULL otherwise (MySQL-safe unique). |
| `created_at` | DateTimeField | blank=True | 无 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['position', 'scenario', 'model__name']`
- 唯一约束 `(policy, scenario, model)` → `uniq_trial_policy_scenario_model`

---

### ManagedFile

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ManagedFile` |
| 数据库表名 | `file_manager_managedfile` |
| 模型说明 | 用户文件元数据与 OSS 对象键。 |
| 核心功能 | 1. 业务挂载维度；2. soft_delete。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `file_uuid` | UUIDField | NOT NULL、UNIQUE、default=callable | 唯一索引 | — |
| `file_path` | CharField(1024) | NOT NULL、blank=True、default='' | 无 | — |
| `original_name` | CharField(255) | NOT NULL | 无 | — |
| `file_ext` | CharField(32) | NOT NULL、blank=True、default='' | 无 | — |
| `mime_type` | CharField(128) | NOT NULL、blank=True、default='application/octet-stream' | 无 | — |
| `file_size` | BigIntegerField | NOT NULL、default=0 | 无 | — |
| `file_md5` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `is_public` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `business_type` | CharField(64) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `business_id` | CharField(64) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `object_key` | CharField(1024) | NOT NULL、blank=True、default='' | 无 | — |
| `storage_type` | CharField(32) | NOT NULL、blank=True、default='oss' | 无 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `deleted_at` | DateTimeField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |
| `updated_at` | DateTimeField | blank=True | 普通索引 | — |

#### 元数据配置

- 默认排序：`['-created_at', '-id']`
- 联合索引 `(user, is_deleted, updated_at)`
- 联合索引 `(user, business_type, business_id, is_deleted)`

---

### AdminRole

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminRole` |
| 数据库表名 | `backoffice_adminrole` |
| 模型说明 | 后台角色。 |
| 核心功能 | 1. name/code 唯一；2. 启用开关。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `name` | CharField(64) | NOT NULL、UNIQUE | 唯一索引 | — |
| `code` | CharField(64) | NOT NULL、UNIQUE | 唯一索引 | — |
| `description` | CharField(255) | NOT NULL、blank=True、default='' | 无 | — |
| `is_active` | BooleanField | NOT NULL、default=True | 普通索引 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['name', 'id']`

---

### AdminPermission

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminPermission` |
| 数据库表名 | `backoffice_adminpermission` |
| 模型说明 | 后台权限点。 |
| 核心功能 | 1. code 唯一；2. 菜单/按钮/API 类型。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `name` | CharField(128) | NOT NULL | 无 | — |
| `code` | CharField(128) | NOT NULL、UNIQUE | 唯一索引 | — |
| `permission_type` | CharField(16) | NOT NULL、choices 枚举 | 普通索引 | — |
| `path` | CharField(255) | NOT NULL、blank=True、default='' | 无 | — |
| `method` | CharField(16) | NOT NULL、blank=True、default='' | 无 | — |
| `parent_code` | CharField(128) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `is_active` | BooleanField | NOT NULL、default=True | 普通索引 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 默认排序：`['permission_type', 'code', 'id']`

---

### AdminRolePermission

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminRolePermission` |
| 数据库表名 | `backoffice_adminrolepermission` |
| 模型说明 | 角色与权限多对多。 |
| 核心功能 | 1. 联合唯一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `role` | ForeignKey(AdminRole) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `permission` | ForeignKey(AdminPermission) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 唯一约束 `(role, permission)` → `uniq_admin_role_permission`

---

### AdminUserRole

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminUserRole` |
| 数据库表名 | `backoffice_adminuserrole` |
| 模型说明 | 用户与角色绑定。 |
| 核心功能 | 1. 联合唯一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `role` | ForeignKey(AdminRole) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 唯一约束 `(user, role)` → `uniq_admin_user_role`

---

### AdminAuditLog

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminAuditLog` |
| 数据库表名 | `backoffice_adminauditlog` |
| 模型说明 | 后台操作审计。 |
| 核心功能 | 1. 请求与响应摘要 JSON。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NULL、blank=True、on_delete=SET_NULL | 外键索引 | — |
| `action` | CharField(128) | NOT NULL | 普通索引 | — |
| `resource_type` | CharField(64) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `resource_id` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `method` | CharField(16) | NOT NULL、blank=True、default='' | 无 | — |
| `path` | CharField(255) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `status_code` | IntegerField | NOT NULL、default=0 | 普通索引 | — |
| `request_id` | CharField(64) | NOT NULL、blank=True、default='' | 普通索引 | — |
| `ip_address` | CharField(64) | NOT NULL、blank=True、default='' | 无 | — |
| `user_agent` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `request_payload` | JSONField | NULL、blank=True | 无 | — |
| `response_payload` | JSONField | NULL、blank=True | 无 | — |
| `created_at` | DateTimeField | blank=True | 普通索引 | — |

#### 元数据配置

- 默认排序：`['-created_at', '-id']`

---

### AdminPermissionPreset

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `AdminPermissionPreset` |
| 数据库表名 | `backoffice_adminpermissionpreset` |
| 模型说明 | RBAC 种子幂等标记。 |
| 核心功能 | 1. key 唯一。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `key` | CharField(64) | NOT NULL、UNIQUE | 唯一索引 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |

#### 元数据配置

- 无额外表级索引/约束（或仅字段级索引，见上表）

---

### ChatThread

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ChatThread` |
| 数据库表名 | `chat_sync_chatthread` |
| 模型说明 | 聊天会话（UUID 主键）。 |
| 核心功能 | 1. 用户隔离；2. 软删；3. 同步 server_updated_at。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | UUIDField | PRIMARY KEY | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `patient_id` | UUIDField | NULL、blank=True | 普通索引 | — |
| `title` | CharField(255) | NOT NULL、default='New Chat' | 无 | — |
| `scenario` | CharField(32) | NOT NULL、default=ChatThread.Scenario.CHAT、choices 枚举 | 无 | — |
| `is_deleted` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `created_at` | DateTimeField | blank=True | 无 | — |
| `updated_at` | DateTimeField | blank=True | 无 | — |
| `server_updated_at` | DateTimeField | blank=True | 普通索引 | — |

#### 元数据配置

- 默认排序：`['-updated_at']`
- 唯一约束 `(user, id)` → `uniq_chat_thread_user_thread`

---

### ChatMessage

| 项目 | 详情 |
| --- | --- |
| 模型类名 | `ChatMessage` |
| 数据库表名 | `chat_sync_chatmessage` |
| 模型说明 | 会话内消息。 |
| 核心功能 | 1. 客户端/服务端消息 ID 唯一；2. 投递状态；3. 墓碑删除。 |

#### 字段详细设计

| 字段名 | 数据类型 | 约束 | 索引 | 字段说明 |
| --- | --- | --- | --- | --- |
| `id` | BigIntegerField | PRIMARY KEY、blank=True | 主键索引 | — |
| `user` | ForeignKey(User) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `thread` | ForeignKey(ChatThread) | NOT NULL、on_delete=CASCADE | 外键索引 | — |
| `role` | CharField(16) | NOT NULL、choices 枚举 | 无 | — |
| `kind` | CharField(16) | NOT NULL、default=ChatMessage.Kind.TEXT、choices 枚举 | 无 | — |
| `content` | TextField | NOT NULL、blank=True、default='' | 无 | — |
| `client_message_id` | UUIDField | NOT NULL | 普通索引 | — |
| `server_message_id` | CharField(64) | NOT NULL | 普通索引 | — |
| `delivery_state` | CharField(16) | NOT NULL、default=ChatMessage.DeliveryState.SENT、choices 枚举 | 无 | — |
| `tombstone` | BooleanField | NOT NULL、default=False | 普通索引 | — |
| `metadata` | JSONField | NOT NULL、blank=True、default=callable | 无 | — |
| `created_at` | DateTimeField | NOT NULL | 普通索引 | — |
| `server_updated_at` | DateTimeField | blank=True | 普通索引 | — |

#### 元数据配置

- 默认排序：`['created_at', 'id']`
- 联合索引 `(user, server_updated_at, id)`
- 联合索引 `(thread, created_at, id)`
- 唯一约束 `(user, client_message_id)` → `uniq_chat_message_user_client_id`
- 唯一约束 `(user, server_message_id)` → `uniq_chat_message_user_server_id`

---
