from django.conf import settings
from django.db import models
from django.utils import timezone


class ScenarioKey(models.TextChoices):
    """与客户端及 bootstrap `scenarios` 键名一致的固定场景枚举。"""

    CHAT = "chat"
    EMBEDDING = "embedding"
    VOICE = "voice"
    MEDICAL_STRUCTURED_EXTRACTION = "medical_structured_extraction"
    MEDICAL_DOCUMENT_TYPE_RECOGNITION = "medical_document_type_recognition"
    MEDICAL_CASE_EXTRACTION = "medical_case_extraction"
    HEALTH_EXAM_EXTRACTION = "health_exam_extraction"
    MEDICAL_REPORT_EXTRACTION = "medical_report_extraction"
    PRESCRIPTION_EXTRACTION = "prescription_extraction"
    MEDICATION_EXTRACTION = "medication_extraction"
    MEDICINE_BOX_EXTRACTION = "medicine_box_extraction"
    OPTIMIZATION_TEXT = "optimization_text"
    OPTIMIZATION_VISUAL = "optimization_visual"
    CONTEXT_FOLDING = "context_folding"
    ROUTER = "router"
    MODEL_CONFIG = "model_config"
    REPORT_INTERPRETATION = "report_interpretation"
    NUTRITION_INTAKE_EXTRACTION = "nutrition_intake_extraction"
    MEDICAL_EXAM_PLAN_GENERATION = "medical_exam_plan_generation"


class IdentityKind(models.TextChoices):
    """绑定行身份：普通模型或智能体。"""

    MODEL = "model"
    AGENT = "agent"


class SparkToolName(models.TextChoices):
    """Spark 平台工具枚举（与客户端 ``ToolingModels.swift`` 的 ``SparkToolName`` 对齐）。

    新增或重命名工具时须同步（保持 rawValue 一致）：
    - SparkClient/Projects/Core/AIRuntime/ToolHub/Models/ToolingModels.swift
    - SparkClient/Projects/Core/AIRuntime/ToolHub/ToolHub.swift（schema / execute）
    - SparkClient/Projects/Core/AIRuntime/ToolHub/Executors/
    - SparkClient/Projects/App/Resources/*/ToolPrompts.strings（tool.summary.* / tool.param.*）
    - SparkClient/Projects/App/Resources/*/Localizable.strings（ai_settings.tools.*）
    """

    # 健康类（Apple Health / 结构化卡片 / 问报告）
    FETCH_STEP_DETAILS = "fetch_step_details", "步数详情"
    FETCH_ENERGY_DETAILS = "fetch_energy_details", "能量详情"
    FETCH_NUTRITION_DETAILS = "fetch_nutrition_details", "营养详情"
    MAKE_NUTRITION_DATA = "make_nutrition_data", "生成营养数据"
    SHOW_MEDICAL_RISK_NOTICE = "show_medical_risk_notice", "医疗风险提示卡片"
    FETCH_SLEEP_DETAILS = "fetch_sleep_details", "睡眠详情"
    FETCH_WORKOUT_DETAILS = "fetch_workout_details", "运动详情"
    GENERATE_STRUCTURED_HEALTH_CARD = "generate_structured_health_card", "生成结构化健康卡片"
    LIST_MEMBER_HEALTH_SOURCES = "list_member_health_sources", "检索成员健康资料"
    GET_HEALTH_RESOURCE_REFERENCE = "get_health_resource_reference", "获取健康资料引用"
    GET_HEALTH_RESOURCE_CONTEXT = "get_health_resource_context", "获取健康资料解读上下文"

    # 知识类
    SEARCH_KNOWLEDGE_BAG = "search_knowledge_bag", "搜索知识库"
    CREATE_KNOWLEDGE_DOCUMENT = "create_knowledge_document", "创建知识文档"

    # 日历类
    SEARCH_CALENDAR_AND_REMINDERS = "search_calendar_and_reminders", "搜索日历与提醒"
    WRITE_SYSTEM_EVENT = "write_system_event", "写入系统事件"

    # 位置类
    QUERY_LOCATION = "query_location", "查询位置"
    GET_CURRENT_LOCATION = "get_current_location", "获取当前位置"
    SEARCH_NEARBY_LOCATIONS = "search_nearby_locations", "搜索附近地点"
    GET_ROUTE = "get_route", "路线规划"
    QUERY_WEATHER = "query_weather", "查询天气"

    # 记忆类
    SAVE_MEMORY = "save_memory", "保存记忆"
    RETRIEVE_MEMORY = "retrieve_memory", "检索记忆"
    UPDATE_MEMORY = "update_memory", "更新记忆"

    # UI 交互类
    GENERATE_CHAT_TITLE = "generate_chat_title", "生成会话标题"
    SHOW_CUSTOM_MESSAGE_CARD = "show_custom_message_card", "展示消息卡片"
    ASK_USER_QUESTION = "ask_user_question", "询问用户"

    # 成员类
    GET_CURRENT_MEMBER = "get_current_member", "获取当前成员"
    REQUEST_MEMBER_SELECTION = "request_member_selection", "请求选择成员"
    SWITCH_MEMBER = "switch_member", "切换成员"
    FIND_MEMBER = "find_member", "查找成员"
    QUERY_MEMBER_PROFILE = "query_member_profile", "查询成员资料"

    # 网络类
    SEARCH_ONLINE = "search_online", "联网搜索"
    INSERT_HEALTH_CITATION_SOURCES = "insert_health_citation_sources", "插入健康引用来源"
    READ_WEB_PAGE = "read_web_page", "读取网页"
    SEARCH_ARXIV_PAPERS = "search_arxiv_papers", "搜索 arXiv 论文"
    EXTRACT_REMOTE_FILE_CONTENT = "extract_remote_file_content", "提取远程文件内容"

    # 系统 / 画布 / 任务类
    CREATE_CANVAS = "create_canvas", "创建画布"
    EDIT_CANVAS = "edit_canvas", "编辑画布"
    QUERY_TASKS_BY_MEMBER = "query_tasks_by_member", "查询成员任务"
    GENERATE_TASK = "generate_task", "生成任务"


class AIScenarioModelBinding(models.Model):
    """场景与目录模型绑定；每场景仅一条默认；MySQL 下用 default_marker 哨兵保证唯一；列注释见 db_comment。"""

    scenario = models.CharField(max_length=64, choices=ScenarioKey.choices, db_index=True, db_comment="场景key")
    identity = models.CharField(max_length=16, choices=IdentityKind.choices, default=IdentityKind.MODEL, db_comment="model或agent")
    model = models.ForeignKey("ai_config.AIModelCatalog", on_delete=models.PROTECT, related_name="scenario_bindings", db_comment="目录模型")
    display_name = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_comment="场景内展示名称；agent可配置业务名称如报告解读助手",
    )
    temperature = models.FloatField(default=0.2, db_comment="生成温度")
    max_tokens = models.IntegerField(default=2048, db_comment="最大输出token")
    position = models.IntegerField(default=0, db_index=True, db_comment="场景内排序")
    is_default = models.BooleanField(default=False, db_index=True, db_comment="是否场景默认")
    is_active = models.BooleanField(default=True, db_index=True, db_comment="是否启用")
    default_marker = models.CharField(max_length=80, null=True, blank=True, unique=True, db_index=True, db_comment="默认时为scenario:default否则NULL")
    system_provision = models.TextField(blank=True, default="", db_comment="场景绑定systemProvision_bootstrap优先试用策略行覆盖")
    brief_description = models.TextField(blank=True, default="", db_comment="场景绑定briefDescription_bootstrap优先试用策略行覆盖")
    ai_tool_scenarios = models.JSONField(default=list, blank=True, db_comment="场景绑定aiToolScenarios_JSON_bootstrap优先试用策略行覆盖")
    related_task_codes = models.JSONField(default=list, blank=True, db_comment="场景绑定关联小任务唯一编码列表")
    updated_at = models.DateTimeField(auto_now=True, db_comment="更新时间")
    created_at = models.DateTimeField(auto_now_add=True, db_comment="创建时间")

    class Meta:
        ordering = ["scenario", "position", "model__name"]
        db_table_comment = "场景模型绑定：Pro bootstrap 场景列表来源"

    def bootstrap_name(self) -> str:
        """Client-facing row name: agent instance id for agents, catalog name for models."""
        if self.identity == IdentityKind.AGENT:
            return f"agent-{self.pk}-{self.model_id}-{self.model.name}"
        return self.model.name

    def save(self, *args, **kwargs):
        if self.is_default:
            AIScenarioModelBinding.objects.filter(scenario=self.scenario).exclude(pk=self.pk).update(
                is_default=False,
                default_marker=None,
            )
            self.default_marker = f"{self.scenario}:default"
        else:
            self.default_marker = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.scenario}:{self.model.name}"


class AIProviderKeyConfig(models.Model):
    """厂商 API/搜索/工具等接入配置；bootstrap 解析 endpoint 与 api_key；列注释见 db_comment。"""

    class Kind(models.TextChoices):
        API = "api"
        SEARCH = "search"
        TOOL = "tool"

    class Source(models.TextChoices):
        SYSTEM = "system"
        CUSTOM = "custom"

    kind = models.CharField(max_length=16, choices=Kind.choices, db_index=True, db_comment="配置类型api或search或tool")
    name = models.CharField(max_length=128, db_comment="配置展示名")
    company = models.CharField(max_length=64, db_comment="厂商大写键与模型company对齐")
    key = models.CharField(max_length=512, blank=True, default="", db_comment="API密钥或令牌")
    request_url = models.CharField(max_length=512, db_comment="请求基址")
    is_hidden = models.BooleanField(default=False, db_comment="是否隐藏")
    is_using = models.BooleanField(default=False, db_comment="是否当前生效行")
    capability_class = models.CharField(max_length=64, blank=True, default="", db_comment="能力分类标签")
    help = models.CharField(max_length=255, blank=True, default="", db_comment="运营侧帮助说明")
    privacy_policy_url = models.CharField(max_length=512, blank=True, default="", db_comment="隐私政策链接")
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.SYSTEM, db_comment="来源system或custom")
    position = models.IntegerField(default=0, db_comment="同类型下排序")
    is_active = models.BooleanField(default=True, db_index=True, db_comment="是否启用")
    updated_at = models.DateTimeField(auto_now=True, db_comment="更新时间")
    created_at = models.DateTimeField(auto_now_add=True, db_comment="创建时间")

    class Meta:
        ordering = ["kind", "position", "company", "name"]
        db_table_comment = "AI厂商与工具接入配置"
        constraints = [
            models.UniqueConstraint(fields=["kind", "company", "name"], name="uniq_ai_provider_key_kind_company_name"),
        ]

    def __str__(self):
        return f"{self.kind}:{self.company}:{self.name}"


class AIModelCatalog(models.Model):
    """全站模型目录；Pro bootstrap 与客户端 AIScenarioRemoteModelRow 对齐；列注释见 db_comment。"""

    class Source(models.TextChoices):
        SYSTEM = "system"
        CUSTOM = "custom"

    name = models.CharField(max_length=128, unique=True, db_comment="模型唯一标识")
    display_name = models.CharField(max_length=128, db_comment="展示名称")
    position = models.IntegerField(default=0, db_index=True, db_comment="排序权重")
    company = models.CharField(max_length=64, db_comment="厂商")
    is_hidden = models.BooleanField(default=False, db_comment="是否隐藏")
    supports_search = models.BooleanField(default=False, db_comment="支持搜索")
    supports_multimodal = models.BooleanField(default=False, db_comment="支持多模态")
    supports_reasoning = models.BooleanField(default=False, db_comment="支持推理")
    supports_tool_use = models.BooleanField(default=False, db_comment="支持工具调用")
    supports_voice_gen = models.BooleanField(default=False, db_comment="支持语音生成")
    supports_image_gen = models.BooleanField(default=False, db_comment="支持图像生成")
    price_tier = models.PositiveSmallIntegerField(default=0, db_comment="价格档位0-3")
    supports_text = models.BooleanField(default=True, db_comment="支持文本")
    reasoning_controllable = models.BooleanField(default=False, db_comment="推理可控")
    icon = models.CharField(max_length=128, blank=True, default="", db_comment="图标SF符号或标识")
    related_task_codes = models.JSONField(default=list, blank=True, db_comment="关联小任务唯一编码列表")
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.SYSTEM, db_comment="来源system或custom")
    is_active = models.BooleanField(default=True, db_index=True, db_comment="是否启用")
    updated_at = models.DateTimeField(auto_now=True, db_comment="更新时间")
    created_at = models.DateTimeField(auto_now_add=True, db_comment="创建时间")

    class Meta:
        ordering = ["position", "name"]
        db_table_comment = "AI模型目录：能力与展示字段；绑定场景见 AIScenarioModelBinding。"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_tier__gte=0) & models.Q(price_tier__lte=3),
                name="aimodelcatalog_price_tier_0_3",
            ),
        ]

    def __str__(self):
        return self.name


class SmallTask(models.Model):
    """AI 小任务配置；客户端可按 code 与模型关联。"""

    class Source(models.TextChoices):
        LOCAL = "Local", "本地任务"
        SERVICE = "Service", "服务任务"

    id = models.AutoField(primary_key=True, verbose_name="小任务ID")
    name = models.CharField(max_length=100, verbose_name="小任务名称")
    code = models.CharField(max_length=50, unique=True, blank=True, verbose_name="唯一编码", help_text="格式：Local_数字 或 Service_数字")
    brief = models.CharField(max_length=255, blank=True, default="", verbose_name="小任务简介")
    prompt = models.TextField(verbose_name="任务设定/Prompt")
    icon = models.CharField(max_length=100, blank=True, default="", verbose_name="图标")
    tool_list = models.JSONField(default=list, blank=True, verbose_name="调用工具列表")
    source = models.CharField(max_length=10, choices=Source.choices, verbose_name="任务来源")
    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="软删除状态")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["source", "id"]
        db_table_comment = "AI小任务配置：本地/服务任务定义，按code与模型关联"

    def save(self, *args, **kwargs):
        if not self.code:
            super().save(*args, **kwargs)
            self.code = f"{self.source}_{self.pk}"
            return super().save(update_fields=["code", "updated_at"])
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code}:{self.name}"


class AIBootstrapProfile(models.Model):
    """客户端旧版 bootstrap 偏好项占位；列注释见 db_comment。"""

    key = models.CharField(max_length=32, unique=True, default="default", db_comment="配置档主键")
    choose_embedding_model = models.CharField(max_length=128, blank=True, default="", db_comment="向量嵌入模型名")
    optimization_text_model = models.CharField(max_length=128, blank=True, default="", db_comment="文本优化默认模型")
    optimization_visual_model = models.CharField(max_length=128, blank=True, default="", db_comment="视觉优化默认模型")
    text_to_speech_model = models.CharField(max_length=128, blank=True, default="", db_comment="语音合成模型")
    use_knowledge = models.BooleanField(default=True, db_comment="是否启用知识库")
    knowledge_count = models.IntegerField(default=5, db_comment="知识检索条数")
    knowledge_similarity = models.FloatField(default=0.75, db_comment="知识相似度阈值")
    use_search = models.BooleanField(default=True, db_comment="是否启用联网搜索")
    bilingual_search = models.BooleanField(default=False, db_comment="是否双语搜索")
    search_count = models.IntegerField(default=3, db_comment="搜索条数")
    use_map = models.BooleanField(default=False, db_comment="是否启用地图工具")
    use_calendar = models.BooleanField(default=False, db_comment="是否启用日历工具")
    use_weather = models.BooleanField(default=False, db_comment="是否启用天气工具")
    use_canvas = models.BooleanField(default=False, db_comment="是否启用画布")
    use_code = models.BooleanField(default=False, db_comment="是否启用代码能力")
    updated_at = models.DateTimeField(auto_now=True, db_comment="更新时间")
    created_at = models.DateTimeField(auto_now_add=True, db_comment="创建时间")

    class Meta:
        ordering = ["-updated_at"]
        db_table_comment = "AI bootstrap 用户偏好配置档"

    def __str__(self):
        return f"bootstrap:{self.key}"


class TrialApplication(models.Model):
    """用户试用 Pro 的申请与状态；列注释见 db_comment。"""

    class Status(models.TextChoices):
        NONE = "none"
        PENDING = "pending"
        ACTIVE = "active"
        REJECTED = "rejected"
        EXPIRED = "expired"

    class GrantSource(models.TextChoices):
        AUTO = "auto"
        MANUAL = "manual"
        APPLICATION = "application"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trial_application", db_comment="用户")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NONE, db_index=True, db_comment="试用状态")
    grant_source = models.CharField(max_length=16, choices=GrantSource.choices, default=GrantSource.AUTO, db_comment="授权来源")
    started_at = models.DateTimeField(null=True, blank=True, db_comment="试用开始时间")
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True, db_comment="试用到期时间")
    applied_at = models.DateTimeField(null=True, blank=True, db_comment="申请提交时间")
    approved_at = models.DateTimeField(null=True, blank=True, db_comment="审核通过时间")
    rejected_at = models.DateTimeField(null=True, blank=True, db_comment="拒绝时间")
    note = models.CharField(max_length=255, blank=True, default="", db_comment="申请或审核备注")
    created_at = models.DateTimeField(auto_now_add=True, db_comment="创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_comment="更新时间")

    class Meta:
        ordering = ["-updated_at"]
        db_table_comment = "用户试用申请与周期"

    def __str__(self):
        return f"trial:{self.user_id}:{self.status}"

    def is_active_trial(self) -> bool:
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at is None:
            return False
        return self.expires_at > timezone.now()


class TrialApplicationRequest(models.Model):
    """试用申请流水（用于统计申请次数、异步自动审核与审计）。"""

    class Source(models.TextChoices):
        AUTO = "auto"
        APPLICATION = "application"
        MANUAL = "manual"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="trial_application_requests",
        on_delete=models.CASCADE,
        db_comment="用户",
    )
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.APPLICATION,
        db_index=True,
        db_comment="流水来源（auto/application/manual）",
    )
    sequence = models.PositiveIntegerField(db_index=True, db_comment="用户累计申请序号（从1开始）")
    status = models.CharField(
        max_length=16,
        choices=TrialApplication.Status.choices,
        default=TrialApplication.Status.PENDING,
        db_index=True,
        db_comment="申请流水状态",
    )
    note = models.CharField(max_length=255, blank=True, default="", db_comment="申请备注")
    auto_approve_after_seconds = models.PositiveIntegerField(null=True, blank=True, db_comment="自动审核延迟秒数")
    scheduled_at = models.DateTimeField(null=True, blank=True, db_comment="自动审核计划执行时间")
    approved_at = models.DateTimeField(null=True, blank=True, db_comment="自动/人工通过时间")
    rejected_at = models.DateTimeField(null=True, blank=True, db_comment="自动/人工拒绝时间")
    created_at = models.DateTimeField(auto_now_add=True, db_comment="创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_comment="更新时间")

    class Meta:
        ordering = ["-created_at"]
        db_table_comment = "试用申请流水"
        constraints = [
            models.UniqueConstraint(fields=["user", "source", "sequence"], name="uniq_trial_application_request_user_source_sequence"),
        ]

    def __str__(self):
        return f"trial-request:{self.user_id}:{self.sequence}:{self.status}"


class TrialModelPolicy(models.Model):
    """试用期内按场景替换模型策略的容器；列注释见 db_comment。"""

    key = models.CharField(max_length=32, unique=True, default="default", db_comment="策略档主键")
    name = models.CharField(max_length=64, default="Default Trial Policy", db_comment="策略展示名")
    description = models.CharField(max_length=255, blank=True, default="", db_comment="策略说明")
    is_active = models.BooleanField(default=True, db_index=True, db_comment="是否启用")
    created_at = models.DateTimeField(auto_now_add=True, db_comment="创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_comment="更新时间")

    class Meta:
        ordering = ["-updated_at"]
        db_table_comment = "试用模型策略主表"

    def __str__(self):
        return f"trial-policy:{self.key}"


class TrialModelPolicyItem(models.Model):
    """某试用策略下某场景的模型行；默认行用 trial_default_marker 哨兵；列注释见 db_comment。"""

    policy = models.ForeignKey(TrialModelPolicy, on_delete=models.CASCADE, related_name="items", db_comment="所属策略")
    scenario = models.CharField(max_length=64, choices=ScenarioKey.choices, db_comment="场景key")
    identity = models.CharField(max_length=16, choices=IdentityKind.choices, default=IdentityKind.MODEL, db_comment="model或agent")
    model = models.ForeignKey("ai_config.AIModelCatalog", on_delete=models.PROTECT, related_name="trial_policy_items", db_comment="目录模型")
    temperature = models.FloatField(default=0.2, db_comment="生成温度")
    max_tokens = models.IntegerField(default=2048, db_comment="最大输出token")
    position = models.IntegerField(default=0, db_comment="策略内排序")
    is_default = models.BooleanField(default=False, db_index=True, db_comment="是否该场景在策略内默认")
    is_active = models.BooleanField(default=True, db_index=True, db_comment="是否启用")
    trial_default_marker = models.CharField(max_length=96, null=True, blank=True, unique=True, db_index=True, db_comment="默认时为p策略id_s场景:default否则NULL")
    system_provision = models.TextField(blank=True, default="", db_comment="试用策略行systemProvision_bootstrap覆盖场景绑定")
    brief_description = models.TextField(blank=True, default="", db_comment="试用策略行briefDescription_bootstrap覆盖场景绑定")
    ai_tool_scenarios = models.JSONField(default=list, blank=True, db_comment="试用策略行aiToolScenarios_JSON_bootstrap覆盖场景绑定")
    related_task_codes = models.JSONField(default=list, blank=True, db_comment="试用策略行关联小任务唯一编码列表")
    created_at = models.DateTimeField(auto_now_add=True, db_comment="创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_comment="更新时间")

    class Meta:
        ordering = ["position", "scenario", "model__name"]
        db_table_comment = "试用策略场景模型明细"
        constraints = [
            models.UniqueConstraint(fields=["policy", "scenario", "model"], name="uniq_trial_policy_scenario_model"),
        ]

    def save(self, *args, **kwargs):
        policy_id = self.policy_id
        if self.is_default and policy_id is not None:
            TrialModelPolicyItem.objects.filter(policy_id=policy_id, scenario=self.scenario).exclude(pk=self.pk).update(
                is_default=False,
                trial_default_marker=None,
            )
            self.trial_default_marker = f"p{policy_id}_s{self.scenario}:default"
        else:
            self.trial_default_marker = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.policy.key}:{self.scenario}:{self.model.name}"
