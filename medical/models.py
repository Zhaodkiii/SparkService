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
    is_deleted = models.BooleanField(default=False, db_index=True, db_comment="是否删除")
    deleted_at = models.DateTimeField(null=True, blank=True, db_comment="软删除时间")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="更新时间")
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
        return self.name


class UserMemberBinding(models.Model):
    """用户与成员的多对多绑定：关系、角色与状态。"""

    class Role(models.TextChoices):
        OWNER = "owner", "owner"
        ADMIN = "admin", "admin"
        EDITOR = "editor", "editor"
        VIEWER = "viewer", "viewer"

    class Status(models.TextChoices):
        ACTIVE = "active", "active"
        REVOKED = "revoked", "revoked"

    user = models.ForeignKey(User, related_name="member_bindings", on_delete=models.CASCADE, db_index=True)
    member = models.ForeignKey(Member, related_name="user_bindings", on_delete=models.CASCADE, db_index=True)
    relationship = models.CharField(max_length=64, default="self")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.OWNER, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    invited_by = models.ForeignKey(
        User,
        related_name="invited_member_bindings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "medical_user_member_binding"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "member"], name="uniq_user_member_binding"),
        ]
        indexes = [
            models.Index(fields=["member", "status"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"binding:user={self.user_id}:member={self.member_id}:{self.relationship}"


class MemberShareInvite(models.Model):
    """远程成员分享邀请（手机号 / 邮箱 / App 内）。"""

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        ACCEPTED = "accepted", "accepted"
        REJECTED = "rejected", "rejected"
        EXPIRED = "expired", "expired"
        CANCELLED = "cancelled", "cancelled"

    class Channel(models.TextChoices):
        PHONE = "phone", "phone"
        EMAIL = "email", "email"
        IN_APP = "in_app", "in_app"

    member = models.ForeignKey(Member, related_name="share_invites", on_delete=models.CASCADE, db_index=True)
    inviter_user = models.ForeignKey(
        User,
        related_name="sent_member_invites",
        on_delete=models.CASCADE,
        db_index=True,
    )
    target_user = models.ForeignKey(
        User,
        related_name="received_member_invites",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
    )
    target_contact = models.CharField(max_length=255, blank=True, default="")
    channel = models.CharField(max_length=16, choices=Channel.choices, db_index=True)
    role = models.CharField(max_length=16, default=UserMemberBinding.Role.VIEWER)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    expires_at = models.DateTimeField(db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "medical_member_share_invite"
        ordering = ["-created_at", "-id"]
        # MySQL 不支持带 condition 的部分唯一约束；pending 去重由 member_invite_service.create_invite 保证。
        indexes = [
            models.Index(fields=["target_user", "status"]),
            models.Index(fields=["member", "status"]),
            models.Index(fields=["member", "inviter_user", "target_user", "status"]),
        ]

    def __str__(self):
        return f"invite:member={self.member_id}:target={self.target_user_id}:{self.status}"


class MemberShareInviteDeliveryLog(models.Model):
    """记录每次邀请通知投递尝试（APNs / 邮件 / 短信）。"""

    class Channel(models.TextChoices):
        APNS = "apns", "apns"
        EMAIL = "email", "email"
        SMS = "sms", "sms"
        NONE = "none", "none"

    class Status(models.TextChoices):
        SENT = "sent", "sent"
        FAILED = "failed", "failed"
        SKIPPED = "skipped", "skipped"

    invite = models.ForeignKey(
        MemberShareInvite,
        on_delete=models.CASCADE,
        related_name="delivery_logs",
        db_index=True,
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    provider_message_id = models.CharField(max_length=255, blank=True, default="")
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "medical_member_share_invite_delivery_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"delivery:invite={self.invite_id}:{self.channel}:{self.status}"


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
    severity = models.CharField(max_length=32, null=True, blank=True)
    case_status = models.CharField(max_length=64, null=True, blank=True)
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
    organization_name = models.CharField(max_length=255, blank=True, null=True, default="")
    department_name = models.CharField(max_length=128, blank=True, default="")
    doctor_name = models.CharField(max_length=128, blank=True, default="")
    findings = models.TextField(blank=True, null=True)
    impression = models.TextField(blank=True, null=True)
    source = models.PositiveSmallIntegerField(choices=Source.choices, default=Source.MANUAL)
    raw_ocr = models.JSONField(null=True, blank=True)
    status = models.PositiveSmallIntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    extra = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "medical_examination_report"
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
    institution_name = models.CharField(max_length=255, blank=True, default="")
    report_no = models.CharField(max_length=128, blank=True, default="", db_index=True)
    exam_date = models.DateField(null=True, blank=True, db_index=True)
    exam_type = models.PositiveSmallIntegerField(choices=ExamType.choices, default=ExamType.ROUTINE)
    summary = models.TextField(blank=True, null=True)
    source = models.PositiveSmallIntegerField(choices=Source.choices, default=Source.MANUAL)
    raw_ocr = models.JSONField(null=True, blank=True)
    status = models.PositiveSmallIntegerField(choices=Status.choices, default=Status.DRAFT, db_index=True)
    extra = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "medical_health_exam_report"
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
        db_table = "medical_med_exam_detail"
        ordering = ["sort_order", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["business_type", "business_id", "is_deleted"]),
            models.Index(fields=["member", "is_deleted"]),
            models.Index(fields=["category", "sub_category", "is_deleted"]),
            models.Index(fields=["business_type", "business_id", "sort_order"]),
        ]


class MedicineBox(MedicalBaseModel):
    """药箱：用户/成员真实拥有的物理药品库存。"""

    class MedicineType(models.TextChoices):
        """预设药品分类（可与自定义文案共同存入 ``medicine_type`` 字段）。"""

        COLD_FEVER = "cold_fever", "感冒发烧"
        GI_DIGESTION = "gi_digestion", "胃肠消化"
        COUGH_THROAT = "cough_throat", "咳嗽咽痛"
        SKIN_BONE = "skin_bone", "皮肤骨痛"
        CHRONIC = "chronic", "慢病用药"
        PEDIATRIC = "pediatric", "儿童用药"
        UNCATEGORIZED = "uncategorized", "未分类"

    member = models.ForeignKey(
        Member,
        related_name="medicine_boxes",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        db_comment="所属家庭成员 ID，可为空；为空表示家庭公共药品",
    )
    medicine_type = models.CharField(max_length=128, blank=True, null=True, db_index=True, db_comment="药品类型（预设编码、中文选项值或自定义文案，可空）")
    medicine_name = models.CharField(max_length=255, db_comment="药品名称（合并原通用名与商品名）")
    brand_name = models.CharField(max_length=255, blank=True, default="", db_comment="品牌名")
    dosage_form = models.CharField(max_length=64, blank=True, default="", db_comment="剂型")
    strength = models.CharField(max_length=128, blank=True, default="", db_comment="规格")
    dose_unit = models.CharField(max_length=32, blank=True, default="", db_comment="剂量数值单位")
    total_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        db_comment="总数量（服药扣减后同步减少，可空）",
    )
    expire_date = models.DateField(null=True, blank=True, db_index=True, db_comment="有效期")
    notes = models.TextField(blank=True, default="", db_comment="备注")
    extra = models.JSONField(default=dict, blank=True, db_comment="扩展字段")

    class Meta:
        db_table = "medical_medicine_box"
        db_table_comment = "药箱：用户/成员的物理药品库存管理。"
        verbose_name = _("药箱")
        verbose_name_plural = _("药箱")
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["user", "member", "is_deleted"]),
            models.Index(fields=["user", "member", "medicine_type", "is_deleted"]),
            models.Index(fields=["expire_date"]),
        ]

    def clean(self):
        if not (self.medicine_name or "").strip():
            raise ValidationError({"medicine_name": _("medicine name is required")})

    def save(self, *args, **kwargs):
        if self.medicine_type is not None:
            stripped = self.medicine_type.strip()
            self.medicine_type = stripped if stripped else None
        self.medicine_name = (self.medicine_name or "").strip()
        self.dose_unit = (self.dose_unit or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class Prescription(MedicalBaseModel):
    """处方：作为服药计划来源，非强制。"""

    class Status(models.TextChoices):
        ACTIVE = "active", "生效中"
        COMPLETED = "completed", "已完成"
        CANCELLED = "cancelled", "已取消"

    member = models.ForeignKey(
        Member,
        related_name="prescriptions",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="就诊人 ID",
    )
    medical_case = models.ForeignKey(
        MedicalCase,
        related_name="prescriptions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        db_comment="关联病例 ID",
    )
    prescriber_name = models.CharField(max_length=128, blank=True, default="", db_comment="开方医生")
    institution_name = models.CharField(max_length=255, blank=True, default="", db_comment="开方机构")
    prescribed_at = models.DateTimeField(null=True, blank=True, db_index=True, db_comment="开方时间")
    diagnosis = models.TextField(blank=True, default="", db_comment="诊断信息")
    prescription_no = models.CharField(max_length=128, blank=True, null=True, db_comment="处方号")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    extra = models.JSONField(default=dict, blank=True, db_comment="扩展字段")

    class Meta:
        db_table = "medical_prescription"
        db_table_comment = "处方信息：服药计划的可选来源。"
        verbose_name = _("处方")
        verbose_name_plural = _("处方")
        ordering = ["-prescribed_at", "-id"]
        indexes = [
            models.Index(fields=["user", "member", "status", "is_deleted"]),
            models.Index(fields=["medical_case", "status", "is_deleted"]),
            models.Index(fields=["prescription_no"]),
        ]

    def clean(self):
        if self.medical_case_id and self.medical_case.member_id != self.member_id:
            raise ValidationError({"medical_case": _("medical_case does not belong to current member")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MedicationPlan(MedicalBaseModel):
    """服药计划：定义独立的用药规则，可选关联药箱与处方。"""

    class FrequencyType(models.TextChoices):
        DAILY = "daily", "每天"
        EVERY_N_DAYS = "every_n_days", "每几天"
        WEEKLY = "weekly", "每周指定星期"

    class Status(models.TextChoices):
        ACTIVE = "active", "执行中"
        PAUSED = "paused", "已暂停"
        COMPLETED = "completed", "已完成"
        CANCELLED = "cancelled", "已取消"

    member = models.ForeignKey(
        Member,
        related_name="medication_plans",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="服药人 ID",
    )
    medical_case = models.ForeignKey(
        MedicalCase,
        related_name="medication_plans",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        db_comment="关联病例 ID",
    )
    medicine_box = models.ForeignKey(
        MedicineBox,
        related_name="plans",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        db_comment="关联药箱药品 ID",
    )
    prescription = models.ForeignKey(
        Prescription,
        related_name="plans",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        db_comment="来源处方 ID",
    )
    drug_name = models.CharField(max_length=255, db_comment="药品名称（计划展示用）")
    dose_per_time = models.CharField(max_length=64, blank=True, default="", db_comment="单次剂量文本")
    dose_value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, db_comment="单次剂量数值")
    dose_unit = models.CharField(max_length=32, blank=True, default="", db_comment="剂量单位")
    frequency_type = models.CharField(
        max_length=20,
        choices=FrequencyType.choices,
        default=FrequencyType.DAILY,
        db_comment="频次类型：每天/每几天/每周",
    )
    every_n_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_comment="间隔天数（仅每几天模式生效）",
    )
    weekly_weekdays = models.JSONField(
        default=list,
        blank=True,
        db_comment="每周服药星期 [1,2,3,6,7]，1=周一…7=周日",
    )
    frequency_text = models.CharField(max_length=255, db_comment="频次说明文本（展示用，可自动生成或手改）")
    reminder_times = models.JSONField(default=list, blank=True, db_comment='提醒时间点 [{"time":"08:00","dose":1}]')
    start_date = models.DateField(db_index=True, db_comment="计划开始日期")
    end_date = models.DateField(null=True, blank=True, db_index=True, db_comment="计划结束日期")
    instructions = models.TextField(blank=True, default="", db_comment="用药说明")
    reminder_enabled = models.BooleanField(default=True, db_comment="是否开启提醒")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    extra = models.JSONField(default=dict, blank=True, db_comment="扩展字段")

    class Meta:
        db_table = "medical_medication_plan"
        db_table_comment = "服药计划：独立的用药规则定义。"
        verbose_name = _("服药计划")
        verbose_name_plural = _("服药计划")
        ordering = ["-start_date", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["user", "member", "status", "is_deleted"]),
            models.Index(fields=["medical_case", "status", "is_deleted"]),
            models.Index(fields=["medicine_box"]),
            models.Index(fields=["prescription"]),
        ]

    def clean(self):
        if self.medical_case_id and self.medical_case.member_id != self.member_id:
            raise ValidationError({"medical_case": _("medical_case does not belong to current member")})
        if self.medicine_box_id:
            from medical.services.medicine_cabinet_service import medicine_box_accessible_for_member

            medicine_box = MedicineBox.objects.filter(pk=self.medicine_box_id).first()
            if medicine_box is None:
                self.medicine_box_id = None
            elif not medicine_box_accessible_for_member(medicine_box=medicine_box, member=self.member):
                raise ValidationError({"medicine_box": _("medicine_box does not belong to current member")})
        if self.prescription_id and self.prescription.member_id != self.member_id:
            raise ValidationError({"prescription": _("prescription does not belong to current member")})
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("end_date cannot be earlier than start_date")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MedicationReminderLocalAuthorization(models.Model):
    """计划级本机提醒授权：当前用户是否同意为某个非本人服药计划创建本地提醒。"""

    user = models.ForeignKey(
        User,
        related_name="medication_reminder_local_authorizations",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="接收本机提醒的登录用户 ID",
    )
    member = models.ForeignKey(
        Member,
        related_name="medication_reminder_local_authorizations",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="服药计划所属成员 ID",
    )
    medication_plan = models.ForeignKey(
        MedicationPlan,
        related_name="local_authorizations",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="具体服药计划 ID",
    )
    enabled = models.BooleanField(default=True, db_index=True, db_comment="是否启用本机提醒授权")
    source = models.CharField(max_length=64, blank=True, default="", db_comment="授权来源")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_comment="创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, db_comment="更新时间")

    class Meta:
        db_table = "medical_medication_reminder_local_authorization"
        db_table_comment = "计划级本机提醒授权：当前用户是否同意为非本人计划创建本地提醒。"
        verbose_name = _("用药提醒本机授权")
        verbose_name_plural = _("用药提醒本机授权")
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "medication_plan"],
                name="uniq_user_medication_plan_local_auth",
            )
        ]
        indexes = [
            models.Index(fields=["user", "enabled"]),
            models.Index(fields=["member", "enabled"]),
            models.Index(fields=["medication_plan", "enabled"]),
        ]

    def clean(self):
        if self.medication_plan_id and self.member_id and self.medication_plan.member_id != self.member_id:
            raise ValidationError({"member": _("member does not match medication_plan.member")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MedicationRecord(MedicalBaseModel):
    """服药记录：计划剂次的执行打卡事实表。"""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "待服药"
        TAKEN = "taken", "已服药"
        SKIPPED = "skipped", "已漏服"
        SNOOZED = "snoozed", "已稍后提醒"

    member = models.ForeignKey(
        Member,
        related_name="medication_records",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="服药人 ID",
    )
    plan = models.ForeignKey(
        MedicationPlan,
        related_name="records",
        on_delete=models.CASCADE,
        db_index=True,
        db_comment="所属服药计划 ID",
    )
    scheduled_at = models.DateTimeField(db_index=True, db_comment="计划服药时间")
    taken_at = models.DateTimeField(null=True, blank=True, db_index=True, db_comment="实际服药时间")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    planned_dose = models.CharField(max_length=64, db_comment="计划剂量")
    actual_dose = models.CharField(max_length=64, blank=True, default="", db_comment="实际服用剂量")
    dose_sequence = models.PositiveSmallIntegerField(default=1, db_comment="当日第几次服药")
    timezone = models.CharField(max_length=64, default="UTC", db_index=True, db_comment="时区")
    notes = models.TextField(blank=True, default="", db_comment="备注")
    extra = models.JSONField(default=dict, blank=True, db_comment="扩展字段")

    class Meta:
        db_table = "medical_medication_record"
        db_table_comment = "服药记录：独立的服药执行打卡数据。"
        verbose_name = _("服药记录")
        verbose_name_plural = _("服药记录")
        ordering = ["-scheduled_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "scheduled_at", "dose_sequence"], name="uniq_plan_schedule_sequence")
        ]
        indexes = [
            models.Index(fields=["user", "member", "scheduled_at", "status"]),
            models.Index(fields=["plan", "status"]),
        ]

    def clean(self):
        if self.plan_id and self.plan.member_id != self.member_id:
            raise ValidationError({"plan": _("plan does not belong to current member")})

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
        db_table = "medical_model_change_log"
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
