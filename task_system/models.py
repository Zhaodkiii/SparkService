from django.contrib.auth.models import User
from django.db import models


class TaskType(models.IntegerChoices):
    MEDICAL = 0, "medical"
    EXERCISE = 1, "exercise"
    DIET = 2, "diet"


class TaskStatus(models.IntegerChoices):
    PENDING = 0, "pending"
    COMPLETED = 1, "completed"
    CANCELED = 2, "canceled"


class TaskRepeatType(models.IntegerChoices):
    NONE = 0, "none"
    DAILY = 1, "daily"
    WEEKLY = 2, "weekly"


class TaskPriority(models.IntegerChoices):
    HIGH = 0, "high"
    MEDIUM = 1, "medium"
    LOW = 2, "low"


class TaskSource(models.IntegerChoices):
    MANUAL = 0, "manual"
    AI = 1, "ai"
    REPORT = 2, "report"


class TaskSubRelatedType(models.TextChoices):
    MEDICAL = "task_medical", "task_medical"
    EXERCISE = "task_exercise", "task_exercise"
    DIET = "task_diet", "task_diet"


class TaskExecutionStatus(models.IntegerChoices):
    DONE = 1, "done"
    SKIPPED = 2, "skipped"
    FAILED = 3, "failed"


class TaskNotificationChannel(models.TextChoices):
    LOCAL = "local", "local"
    APNS = "apns", "apns"
    SMS = "sms", "sms"


class TaskNotificationStatus(models.IntegerChoices):
    PENDING = 0, "pending"
    SENT = 1, "sent"
    FAILED = 2, "failed"


class TaskBaseModel(models.Model):
    """任务域基础字段。

    统一提供扩展字段与时间戳，便于后续 AI 策略透传和增量同步。
    """

    extra = models.JSONField("扩展信息", default=dict, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True, db_index=True)

    class Meta:
        abstract = True
        verbose_name = "任务基础模型"
        verbose_name_plural = "任务基础模型"


class Task(TaskBaseModel):
    """任务总表（主任务）。"""

    member = models.ForeignKey("medical.Member", verbose_name="成员", related_name="tasks", on_delete=models.CASCADE, db_index=True)
    creator = models.ForeignKey(User, verbose_name="创建人", related_name="created_tasks", on_delete=models.CASCADE, db_index=True)
    title = models.CharField("标题", max_length=255)
    description = models.TextField("描述", blank=True, default="")
    type = models.PositiveSmallIntegerField("任务类型", choices=TaskType.choices, db_index=True)
    status = models.PositiveSmallIntegerField("任务状态", choices=TaskStatus.choices, default=TaskStatus.PENDING, db_index=True)
    start_time = models.DateTimeField("开始时间", null=True, blank=True, db_index=True)
    due_time = models.DateTimeField("截止时间", null=True, blank=True, db_index=True)
    repeat_type = models.PositiveSmallIntegerField("重复类型", choices=TaskRepeatType.choices, default=TaskRepeatType.NONE)
    priority = models.PositiveSmallIntegerField("优先级", choices=TaskPriority.choices, default=TaskPriority.MEDIUM, db_index=True)
    business_type = models.CharField("业务类型", max_length=64, blank=True, default="", db_index=True)
    business_id = models.CharField("业务 ID", max_length=64, blank=True, default="", db_index=True)
    source = models.PositiveSmallIntegerField("任务来源", choices=TaskSource.choices, default=TaskSource.MANUAL, db_index=True)
    notification_id = models.CharField("通知标识", max_length=128, blank=True, default="", db_index=True)
    notification_enabled = models.BooleanField("通知已开启", default=True, db_index=True)

    class Meta:
        db_table = "task"
        verbose_name = "任务"
        verbose_name_plural = "任务"
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["member", "status"]),
            models.Index(fields=["member", "updated_at"]),
            models.Index(fields=["member", "type", "status"]),
            models.Index(fields=["member", "business_type", "business_id"]),
        ]


class TaskMedical(TaskBaseModel):
    task = models.OneToOneField(Task, verbose_name="主任务", related_name="task_medical", on_delete=models.CASCADE)
    status = models.PositiveSmallIntegerField("任务状态", choices=TaskStatus.choices, default=TaskStatus.PENDING, db_index=True)
    reminder_time = models.DateTimeField("提醒时间", null=True, blank=True, db_index=True)
    medical_task_type = models.CharField("医疗任务类型", max_length=64, db_index=True)
    description = models.TextField("描述", blank=True, default="")
    source = models.CharField("来源", max_length=16, default="manual")
    created_by = models.ForeignKey(User, verbose_name="创建人", related_name="medical_tasks_created", on_delete=models.CASCADE)
    operator = models.ForeignKey(User, verbose_name="操作人", related_name="medical_tasks_operated", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = "task_medical"
        verbose_name = "医疗任务"
        verbose_name_plural = "医疗任务"
        ordering = ["-updated_at", "-id"]


class TaskExercise(TaskBaseModel):
    task = models.OneToOneField(Task, verbose_name="主任务", related_name="task_exercise", on_delete=models.CASCADE)
    status = models.PositiveSmallIntegerField("任务状态", choices=TaskStatus.choices, default=TaskStatus.PENDING, db_index=True)
    exercise_type = models.CharField("运动类型", max_length=64, db_index=True)
    duration_min = models.PositiveIntegerField("时长（分钟）", default=0)
    intensity = models.CharField("强度", max_length=16, default="medium")
    description = models.TextField("描述", blank=True, default="")
    source = models.CharField("来源", max_length=16, default="manual")
    created_by = models.ForeignKey(User, verbose_name="创建人", related_name="exercise_tasks_created", on_delete=models.CASCADE)
    operator = models.ForeignKey(User, verbose_name="操作人", related_name="exercise_tasks_operated", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = "task_exercise"
        verbose_name = "运动任务"
        verbose_name_plural = "运动任务"
        ordering = ["-updated_at", "-id"]


class TaskDiet(TaskBaseModel):
    task = models.OneToOneField(Task, verbose_name="主任务", related_name="task_diet", on_delete=models.CASCADE)
    status = models.PositiveSmallIntegerField("任务状态", choices=TaskStatus.choices, default=TaskStatus.PENDING, db_index=True)
    meal_type = models.CharField("餐次类型", max_length=32, default="breakfast", db_index=True)
    calorie_target = models.PositiveIntegerField("目标热量", default=0)
    food_recommend = models.JSONField("食物建议", default=list, blank=True)
    description = models.TextField("描述", blank=True, default="")
    source = models.CharField("来源", max_length=16, default="manual")
    created_by = models.ForeignKey(User, verbose_name="创建人", related_name="diet_tasks_created", on_delete=models.CASCADE)
    operator = models.ForeignKey(User, verbose_name="操作人", related_name="diet_tasks_operated", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = "task_diet"
        verbose_name = "饮食任务"
        verbose_name_plural = "饮食任务"
        ordering = ["-updated_at", "-id"]


class TaskExecution(models.Model):
    """任务执行记录：用于统计、回放与 AI 反馈。"""

    task = models.ForeignKey(Task, verbose_name="任务", related_name="executions", on_delete=models.CASCADE, db_index=True)
    user = models.ForeignKey(User, verbose_name="执行用户", related_name="task_executions", on_delete=models.CASCADE, db_index=True)
    member = models.ForeignKey("medical.Member", verbose_name="成员", related_name="task_executions", on_delete=models.CASCADE, db_index=True)
    business_type = models.CharField("业务类型", max_length=64, blank=True, default="", db_index=True)
    business_id = models.CharField("业务 ID", max_length=64, blank=True, default="", db_index=True)
    related_sub_type = models.CharField("关联子类型", max_length=32, choices=TaskSubRelatedType.choices, blank=True, default="")
    related_sub_id = models.PositiveBigIntegerField("关联子 ID", null=True, blank=True)
    status = models.PositiveSmallIntegerField("执行状态", choices=TaskExecutionStatus.choices, db_index=True)
    executed_at = models.DateTimeField("执行时间", db_index=True)
    value = models.JSONField("执行数据", default=dict, blank=True)
    notes = models.TextField("备注", blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "task_execution"
        verbose_name = "任务执行记录"
        verbose_name_plural = "任务执行记录"
        ordering = ["-executed_at", "-id"]
        indexes = [
            models.Index(fields=["task", "executed_at"]),
            models.Index(fields=["member", "status", "executed_at"]),
        ]


class TaskNotification(TaskBaseModel):
    """任务提醒策略（服务端可选调度 + 客户端本地通知对齐）。"""

    task = models.ForeignKey(Task, verbose_name="任务", related_name="notifications", on_delete=models.CASCADE, db_index=True)
    member = models.ForeignKey("medical.Member", verbose_name="成员", related_name="task_notifications", on_delete=models.CASCADE, db_index=True)
    channel = models.CharField("通知渠道", max_length=16, choices=TaskNotificationChannel.choices, default=TaskNotificationChannel.LOCAL)
    status = models.PositiveSmallIntegerField("通知状态", choices=TaskNotificationStatus.choices, default=TaskNotificationStatus.PENDING, db_index=True)
    template_code = models.CharField("模板编码", max_length=64, default="health_task_default")
    template_params = models.JSONField("模板参数", default=dict, blank=True)
    reminder_time = models.DateTimeField("提醒时间", db_index=True)
    sent_at = models.DateTimeField("发送时间", null=True, blank=True)
    failed_reason = models.CharField("失败原因", max_length=255, blank=True, default="")

    class Meta:
        db_table = "task_notification"
        verbose_name = "任务提醒"
        verbose_name_plural = "任务提醒"
        ordering = ["-reminder_time", "-id"]
        indexes = [
            models.Index(fields=["task", "status"]),
            models.Index(fields=["member", "status", "reminder_time"]),
        ]


class TaskPlan(TaskBaseModel):
    """长期任务计划，用于后续 AI 编排周期策略。"""

    member = models.ForeignKey("medical.Member", verbose_name="成员", related_name="task_plans", on_delete=models.CASCADE, db_index=True)
    creator = models.ForeignKey(User, verbose_name="创建人", related_name="task_plans", on_delete=models.CASCADE, db_index=True)
    title = models.CharField("标题", max_length=255)
    description = models.TextField("描述", blank=True, default="")
    status = models.PositiveSmallIntegerField("计划状态", default=TaskStatus.PENDING, db_index=True)
    start_date = models.DateField("开始日期", null=True, blank=True)
    end_date = models.DateField("结束日期", null=True, blank=True)

    class Meta:
        db_table = "task_plan"
        verbose_name = "任务计划"
        verbose_name_plural = "任务计划"
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["member", "status"]),
            models.Index(fields=["member", "updated_at"]),
        ]
