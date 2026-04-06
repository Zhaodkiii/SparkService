from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SoftDeleteQuerySet(models.QuerySet):
    """统一软删除查询集，避免业务层遗漏 ``is_deleted=False`` 过滤。"""

    def alive(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """默认仅返回未软删除数据的管理器。"""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class MedicalBaseModel(models.Model):
    """医疗相关模型的抽象基类。

    提供：与登录用户的关联、软删除标记与时间字段。
    """

    # 关联用户：一个用户可拥有多个成员/医疗记录；删除用户时级联删除其医疗数据。
    user = models.ForeignKey(User, related_name="%(class)s_items", on_delete=models.CASCADE, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)  # 软删除标记
    deleted_at = models.DateTimeField(null=True, blank=True)  # 软删除时间
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self):
        """标记为已删除并记录删除时间；已删除则不重复执行。"""
        if self.is_deleted:
            return
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class Member(MedicalBaseModel):
    """家庭/档案中的就诊成员（含本人与亲属等）。"""

    class Gender(models.TextChoices):
        MALE = "male"
        FEMALE = "female"
        UNKNOWN = "unknown"

    name = models.CharField(max_length=64)
    gender = models.CharField(max_length=16, choices=Gender.choices, default=Gender.UNKNOWN)
    relationship = models.CharField(max_length=64, default="self")  # 与主账户关系，如 self / 父母等
    birth_date = models.DateField(null=True, blank=True)
    blood_type = models.CharField(max_length=8, blank=True, default="")
    allergies = models.JSONField(default=list, blank=True)
    chronic_conditions = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default="")
    avatar_url = models.CharField(max_length=512, blank=True, default="")
    is_primary = models.BooleanField(default=False, db_index=True)  # 是否主档案/本人优先展示

    class Meta:
        ordering = ["-is_primary", "-updated_at", "-id"]

    def __str__(self):
        return f"{self.name}({self.relationship})"


class MedicalCase(MedicalBaseModel):
    """门诊/住院病历叙事主档（聚合根）。

    主档遵循“瘦身策略”：只保留状态、类型、时间轴入口与摘要字段。
    临床细节由 ``Symptom``/``Visit``/``Surgery``/``FollowUp`` 承载，避免双写冲突。
    """

    class Status(models.IntegerChoices):
        DRAFT = 1, "draft"
        SUBMITTED = 2, "submitted"
        ARCHIVED = 3, "archived"

    member = models.ForeignKey(Member, related_name="medical_cases", on_delete=models.CASCADE, db_index=True)
    record_type = models.CharField(max_length=32, default="custom", db_index=True)
    status = models.PositiveSmallIntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")
    hospital_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    age_at_visit = models.PositiveSmallIntegerField(null=True, blank=True)
    diagnosis_summary = models.TextField(blank=True, default="")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["member", "is_deleted", "created_at"]),
            models.Index(fields=["member", "record_type", "is_deleted", "created_at"]),
            models.Index(fields=["member", "status", "is_deleted", "created_at"]),
            models.Index(fields=["hospital_name"]),
        ]


class Symptom(MedicalBaseModel):
    """病例症状条目。支持结构化持续时间与解剖部位检索。"""

    member = models.ForeignKey(Member, related_name="symptoms", on_delete=models.CASCADE, db_index=True)
    medical_case = models.ForeignKey(MedicalCase, related_name="symptoms", on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=64, blank=True, default="")
    severity = models.CharField(max_length=32, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    duration_value = models.PositiveIntegerField(null=True, blank=True)
    duration_unit = models.CharField(max_length=16, blank=True, default="")
    body_part = models.CharField(max_length=128, blank=True, default="", db_index=True)
    notes = models.TextField(blank=True, default="")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["medical_case", "created_at"]),
            models.Index(fields=["member", "medical_case", "is_deleted", "created_at"]),
            models.Index(fields=["body_part"]),
        ]


class Visit(MedicalBaseModel):
    """就诊节点记录（门诊/急诊/随诊等）。"""

    member = models.ForeignKey(Member, related_name="visits", on_delete=models.CASCADE, db_index=True)
    medical_case = models.ForeignKey(MedicalCase, related_name="visits", on_delete=models.CASCADE, db_index=True)
    visit_type = models.CharField(max_length=32, default="custom")
    visited_at = models.DateTimeField(null=True, blank=True, db_index=True)
    department = models.CharField(max_length=128, blank=True, default="")
    doctor_name = models.CharField(max_length=128, blank=True, default="")
    visit_no = models.CharField(max_length=64, blank=True, default="")
    source_system_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    notes = models.TextField(blank=True, default="")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-visited_at", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["medical_case", "visited_at"]),
            models.Index(fields=["member", "medical_case", "is_deleted", "visited_at"]),
            models.Index(fields=["source_system_id"]),
        ]


class Surgery(MedicalBaseModel):
    """手术/操作记录。包含质控字段与外部系统幂等标识。"""

    member = models.ForeignKey(Member, related_name="surgeries", on_delete=models.CASCADE, db_index=True)
    medical_case = models.ForeignKey(MedicalCase, related_name="surgeries", on_delete=models.CASCADE, db_index=True)
    procedure_name = models.CharField(max_length=255)
    procedure_code = models.CharField(max_length=64, blank=True, default="")
    site = models.CharField(max_length=128, blank=True, default="")
    performed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    surgeon = models.CharField(max_length=128, blank=True, default="")
    anesthesia_type = models.CharField(max_length=128, blank=True, default="")
    incision_level = models.CharField(max_length=8, blank=True, default="")
    asa_class = models.CharField(max_length=8, blank=True, default="")
    source_system_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    notes = models.TextField(blank=True, default="")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-performed_at", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["medical_case", "performed_at"]),
            models.Index(fields=["member", "medical_case", "is_deleted", "performed_at"]),
            models.Index(fields=["source_system_id"]),
        ]


class FollowUp(MedicalBaseModel):
    """随访计划与执行记录。"""

    member = models.ForeignKey(Member, related_name="follow_ups", on_delete=models.CASCADE, db_index=True)
    medical_case = models.ForeignKey(MedicalCase, related_name="follow_ups", on_delete=models.CASCADE, db_index=True)
    planned_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, default="initial", db_index=True)
    method = models.CharField(max_length=32, blank=True, default="")
    outcome = models.TextField(blank=True, default="")
    next_action = models.TextField(blank=True, default="")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-completed_at", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["medical_case", "status", "completed_at"]),
            models.Index(fields=["member", "medical_case", "is_deleted", "completed_at"]),
        ]


class ExaminationReport(MedicalBaseModel):
    """临床检查主表（影像/功能检查/病理等）。"""

    class Source(models.IntegerChoices):
        MANUAL = 1, "manual"
        OCR = 2, "ocr"

    class Status(models.IntegerChoices):
        DRAFT = 1, "draft"
        COMPLETED = 2, "completed"
        REVISED = 3, "revised"
        DISCARDED = 4, "discarded"

    member = models.ForeignKey(Member, related_name="examination_reports", on_delete=models.CASCADE, db_index=True)
    medical_record = models.ForeignKey(
        MedicalCase, related_name="examination_reports", on_delete=models.SET_NULL, null=True, blank=True, db_index=True
    )
    category = models.CharField(max_length=128, blank=True, default="")
    sub_category = models.CharField(max_length=128, blank=True, default="")
    item_name = models.CharField(max_length=255)
    performed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reported_at = models.DateTimeField(null=True, blank=True, db_index=True)
    organization_name = models.CharField(max_length=255)
    department_name = models.CharField(max_length=128, blank=True, default="")
    doctor_name = models.CharField(max_length=128, blank=True, default="")
    findings = models.TextField(blank=True, null=True)
    impression = models.TextField(blank=True, null=True)
    source = models.PositiveSmallIntegerField(choices=Source.choices, default=Source.MANUAL)
    raw_ocr = models.JSONField(null=True, blank=True)
    status = models.PositiveSmallIntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    extra = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "examination_report"
        ordering = ["-reported_at", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["member", "status", "is_deleted"]),
            models.Index(fields=["member", "performed_at", "is_deleted"]),
            models.Index(fields=["member", "reported_at", "is_deleted"]),
        ]


class HealthExamReport(MedicalBaseModel):
    """单次体检报告主表。"""

    class ExamType(models.IntegerChoices):
        ROUTINE = 1, "routine"
        ONBOARDING = 2, "onboarding"
        SPECIAL = 3, "special"
        SENIOR = 4, "senior"

    class Source(models.IntegerChoices):
        MANUAL = 1, "manual"
        OCR = 2, "ocr"
        IMPORTED = 3, "imported"

    class Status(models.IntegerChoices):
        DRAFT = 1, "draft"
        COMPLETED = 2, "completed"
        VERIFIED = 3, "verified"

    member = models.ForeignKey(Member, related_name="health_exam_reports", on_delete=models.CASCADE, db_index=True)
    institution_name = models.CharField(max_length=255)
    report_no = models.CharField(max_length=128, blank=True, default="", db_index=True)
    exam_date = models.DateField(null=True, blank=True, db_index=True)
    exam_type = models.PositiveSmallIntegerField(choices=ExamType.choices, default=ExamType.ROUTINE)
    summary = models.TextField(blank=True, null=True)
    source = models.PositiveSmallIntegerField(choices=Source.choices, default=Source.MANUAL)
    raw_ocr = models.JSONField(null=True, blank=True)
    status = models.PositiveSmallIntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    extra = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "health_exam_report"
        ordering = ["-exam_date", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["member", "exam_date", "is_deleted"]),
            models.Index(fields=["member", "status", "is_deleted"]),
        ]


class MedExamDetail(models.Model):
    """体检与临床检查共用的行级医技结果明细。"""

    class BusinessType(models.TextChoices):
        HEALTH_EXAM_REPORT = "health_exam_report"
        EXAMINATION_REPORT = "examination_report"

    business_type = models.CharField(max_length=32, choices=BusinessType.choices, db_index=True)
    business_id = models.PositiveBigIntegerField(db_index=True)
    member = models.ForeignKey(Member, related_name="med_exam_details", on_delete=models.CASCADE, db_index=True)
    category = models.CharField(max_length=128, blank=True, default="", db_index=True)
    sub_category = models.CharField(max_length=128, blank=True, default="", db_index=True)
    item_name = models.CharField(max_length=255)
    item_code = models.CharField(max_length=64, blank=True, default="")
    result_value = models.CharField(max_length=255, blank=True, default="")
    unit = models.CharField(max_length=64, blank=True, default="")
    reference_range = models.CharField(max_length=255, blank=True, default="")
    flag = models.CharField(max_length=16, blank=True, default="")
    result_at = models.DateTimeField(null=True, blank=True, db_index=True)
    modality = models.CharField(max_length=32, blank=True, default="")
    body_part = models.CharField(max_length=128, blank=True, default="")
    diagnosis = models.TextField(blank=True, null=True)
    extra = models.JSONField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "med_exam_detail"
        ordering = ["sort_order", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["business_type", "business_id", "is_deleted"]),
            models.Index(fields=["member", "is_deleted"]),
            models.Index(fields=["category", "sub_category", "is_deleted"]),
            models.Index(fields=["business_type", "business_id", "sort_order"]),
        ]


class MedicalReport(MedicalBaseModel):
    """广义医疗文书/报告（类型由 report_type 区分）。"""

    member = models.ForeignKey(Member, related_name="medical_reports", on_delete=models.CASCADE, db_index=True)
    medical_case = models.ForeignKey(
        MedicalCase, related_name="medical_reports", on_delete=models.SET_NULL, null=True, blank=True, db_index=True
    )
    report_type = models.CharField(max_length=64, blank=True, default="")
    title = models.CharField(max_length=255)
    hospital = models.CharField(max_length=255, blank=True, default="")
    doctor = models.CharField(max_length=128, blank=True, default="")
    content = models.TextField(blank=True, default="")
    date = models.DateTimeField()

    class Meta:
        ordering = ["-date", "-updated_at", "-id"]


class PrescriptionBatch(MedicalBaseModel):
    """处方批次模型（处方头）。

    一次开具处方或一次用药方案对应一个批次，药品行由 ``Medication`` 表承载。
    该层用于聚合医生/机构/诊断信息，并给提醒与依从性统计提供批次维度入口。
    """

    class Status(models.TextChoices):
        ACTIVE = "active"
        AUDITED = "audited"
        REJECTED = "rejected"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    member = models.ForeignKey(
        Member,
        related_name="prescription_batches",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="所属就诊人 ID",
    )
    medical_case = models.ForeignKey(
        MedicalCase,
        related_name="prescription_batches",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        db_comment="可选来源病例 ID",
    )
    prescriber_name = models.CharField(
        max_length=128, blank=True, default="", help_text=_("开方医生"), db_comment="开方医生姓名"
    )
    institution_name = models.CharField(
        max_length=255, blank=True, default="", help_text=_("开方机构名称"), db_comment="机构名称"
    )
    prescribed_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("开方/方案起始时间"),
        db_comment="开方或方案开始时间",
    )
    diagnosis = models.TextField(blank=True, default="", help_text=_("诊断或适应症摘要"), db_comment="诊断摘要")
    batch_no = models.CharField(
        max_length=128,
        blank=True,
        default="",
        unique=True,
        help_text=_("业务批次号/处方号"),
        db_comment="业务唯一批次号",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    auditor_name = models.CharField(
        max_length=128, blank=True, default="", help_text=_("审核人姓名"), db_comment="审核人姓名"
    )
    audited_at = models.DateTimeField(null=True, blank=True, help_text=_("审核时间"), db_comment="审核时间")
    extra = models.JSONField(default=dict, blank=True, db_comment="扩展字段")

    class Meta:
        db_table = "prescription_batch"
        db_table_comment = "处方批次：一次处方或用药方案的批次头信息。"
        verbose_name = _("处方批次")
        verbose_name_plural = _("处方批次")
        ordering = ["-prescribed_at", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["user", "member", "is_deleted", "prescribed_at"]),
            models.Index(fields=["medical_case"]),
            models.Index(fields=["batch_no"]),
        ]

    def clean(self):
        """约束批次的归属链路，避免跨用户/跨成员串数据。"""
        if self.member_id and self.member.user_id != self.user_id:
            raise ValidationError({"member": _("member does not belong to current user")})
        if self.medical_case_id:
            if self.medical_case.user_id != self.user_id:
                raise ValidationError({"medical_case": _("medical_case does not belong to current user")})
            if self.member_id and self.medical_case.member_id != self.member_id:
                raise ValidationError({"medical_case": _("medical_case.member mismatch with batch.member")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Medication(MedicalBaseModel):
    """用药药品行模型。

    一条记录表示批次下单个药品及其用法用量、提醒规则，供任务引擎拆解为服药计划。
    """

    member = models.ForeignKey(
        Member, related_name="medications", on_delete=models.CASCADE, db_index=True, db_comment="所属就诊人 ID"
    )
    batch = models.ForeignKey(
        PrescriptionBatch, related_name="medications", on_delete=models.CASCADE, db_index=True, db_comment="所属处方批次 ID"
    )
    generic_name = models.CharField(max_length=255, blank=True, default="", db_comment="通用名")
    brand_name = models.CharField(max_length=255, blank=True, default="", db_comment="品牌名")
    drug_name = models.CharField(max_length=255, db_comment="药品显示名")
    dosage_form = models.CharField(max_length=64, blank=True, default="", db_comment="剂型")
    strength = models.CharField(max_length=128, blank=True, default="", db_comment="规格")
    route = models.CharField(max_length=64, blank=True, default="", db_comment="给药途径")
    dose_per_time = models.CharField(max_length=64, blank=True, default="", db_comment="单次剂量文本")
    dose_value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, db_comment="单次剂量数值")
    dose_unit = models.CharField(max_length=32, blank=True, default="", db_comment="单次剂量单位")
    frequency_code = models.CharField(max_length=64, blank=True, default="", db_comment="频次编码")
    period = models.CharField(max_length=16, blank=True, default="", db_comment="频次周期")
    times_per_period = models.PositiveSmallIntegerField(null=True, blank=True, db_comment="每周期次数")
    frequency_text = models.CharField(max_length=255, blank=True, default="", db_comment="频次展示文案")
    duration_days = models.PositiveIntegerField(null=True, blank=True, db_comment="疗程天数")
    instructions = models.TextField(blank=True, default="", db_comment="用药说明")
    reminder_enabled = models.BooleanField(default=True, db_comment="是否启用提醒")
    reminder_times = models.JSONField(default=list, blank=True, db_comment="提醒时间点列表")
    sort_order = models.PositiveIntegerField(default=0, db_comment="批次内排序")
    extra = models.JSONField(default=dict, blank=True, db_comment="扩展字段")

    class Meta:
        db_table = "medication"
        db_table_comment = "用药记录：处方批次下的药品行与提醒规则。"
        verbose_name = _("用药记录")
        verbose_name_plural = _("用药记录")
        ordering = ["sort_order", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["batch", "sort_order"]),
            models.Index(fields=["user", "member", "is_deleted", "created_at"]),
        ]

    def clean(self):
        """校验批次与药品归属的一致性，防止跨成员/跨用户写入。"""
        if self.member_id and self.member.user_id != self.user_id:
            raise ValidationError({"member": _("member does not belong to current user")})
        if self.batch_id:
            if self.batch.user_id != self.user_id:
                raise ValidationError({"batch": _("batch does not belong to current user")})
            if self.member_id and self.batch.member_id != self.member_id:
                raise ValidationError({"batch": _("batch.member mismatch with medication.member")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MedicationTakenRecord(MedicalBaseModel):
    """服药打卡记录模型。

    记录应服时间与实际打卡状态，提供依从性统计（日历、完成率、漏服率）的事实明细。
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled"
        TAKEN = "taken"
        SKIPPED = "skipped"
        SNOOZED = "snoozed"

    member = models.ForeignKey(
        Member,
        related_name="medication_taken_records",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="所属就诊人 ID",
    )
    medication = models.ForeignKey(
        Medication,
        related_name="taken_records",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="对应药品行 ID",
    )
    scheduled_at = models.DateTimeField(db_index=True, db_comment="计划服药时间")
    taken_at = models.DateTimeField(null=True, blank=True, db_comment="实际服药时间")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    dose_sequence = models.PositiveSmallIntegerField(default=1, db_comment="当日第几次")
    actual_dose = models.CharField(max_length=64, blank=True, default="", db_comment="实际服用剂量文本")
    timezone = models.CharField(max_length=64, blank=True, default="UTC", db_index=True, db_comment="打卡时区")
    notes = models.TextField(blank=True, default="", db_comment="备注")
    extra = models.JSONField(default=dict, blank=True, db_comment="扩展字段")

    class Meta:
        db_table = "medication_taken_record"
        db_table_comment = "服药打卡记录：单次应服/已服/漏服事实。"
        verbose_name = _("服药打卡")
        verbose_name_plural = _("服药打卡")
        ordering = ["-scheduled_at", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["medication", "scheduled_at", "dose_sequence"], name="uniq_medication_schedule_sequence"
            )
        ]
        indexes = [
            models.Index(fields=["medication", "scheduled_at", "status"]),
            models.Index(fields=["user", "member", "scheduled_at", "status"]),
        ]

    def clean(self):
        """校验打卡与药品/成员归属一致，避免跨账号串数据。"""
        if self.member_id and self.member.user_id != self.user_id:
            raise ValidationError({"member": _("member does not belong to current user")})
        if self.medication_id:
            if self.medication.user_id != self.user_id:
                raise ValidationError({"medication": _("medication does not belong to current user")})
            if self.member_id and self.medication.member_id != self.member_id:
                raise ValidationError({"medication": _("medication.member mismatch with taken_record.member")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ModelChangeLog(models.Model):
    """药物域审计日志：记录 Who/When/What changed。"""

    user = models.ForeignKey(User, related_name="medical_change_logs", on_delete=models.CASCADE, db_index=True)
    member = models.ForeignKey(Member, related_name="change_logs", on_delete=models.SET_NULL, null=True, blank=True)
    entity = models.CharField(max_length=64, db_index=True)
    entity_id = models.PositiveBigIntegerField(db_index=True)
    action = models.CharField(max_length=32, db_index=True)
    from_status = models.CharField(max_length=32, blank=True, default="")
    to_status = models.CharField(max_length=32, blank=True, default="")
    changed_fields = models.JSONField(default=dict, blank=True)
    trace_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    operator = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "model_change_log"
        db_table_comment = "通用模型审计日志：追踪医疗域关键状态与字段变更。"
        verbose_name = _("模型变更日志")
        verbose_name_plural = _("模型变更日志")
        ordering = ["-created_at", "-id"]


class HealthMetricRecord(MedicalBaseModel):
    """健康指标时间序列（按账户/档案的 ``profile_client_uid`` 同步）。

    与病例、检查报告等不同：本表**不**外键到 :class:`Member`。
    服务端家庭医疗记录按成员维度组织；本表表示某档案维度的云端指标时间线，
    用于同步（例如 iOS 首页运动健康等为当前用户本机数据，云端以此表承载时间线）。
    """

    profile_client_uid = models.UUIDField(db_index=True)  # 客户端档案/用户配置的稳定 UUID
    metric_type = models.CharField(max_length=64, db_index=True)  # 指标类型标识
    value = models.FloatField(default=0)
    unit = models.CharField(max_length=32, default="")
    recorded_at = models.DateTimeField(db_index=True)  # 采样/记录时刻
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-recorded_at", "-updated_at", "-id"]
