from django.conf import settings
from django.db import models
from django.utils import timezone


class AIScenarioConfig(models.Model):
    class Scenario(models.TextChoices):
        CHAT = "chat"
        OPTIMIZATION_TEXT = "optimization_text"
        OPTIMIZATION_VISUAL = "optimization_visual"
        CONTEXT_FOLDING = "context_folding"
        ROUTER = "router"
        MODEL_CONFIG = "model_config"
        REPORT_INTERPRETATION = "report_interpretation"

    class Identity(models.TextChoices):
        MODEL = "model"
        AGENT = "agent"

    scenario = models.CharField(max_length=64, choices=Scenario.choices, unique=True)
    identity = models.CharField(max_length=16, choices=Identity.choices, default=Identity.MODEL)
    model = models.ForeignKey("ai_config.AIModelCatalog", on_delete=models.PROTECT, related_name="scenario_configs")
    temperature = models.FloatField(default=0.2)
    max_tokens = models.IntegerField(default=2048)
    is_active = models.BooleanField(default=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scenario"]

    def __str__(self):
        return f"{self.scenario}:{self.model.name}"


class AIProviderKeyConfig(models.Model):
    class Kind(models.TextChoices):
        API = "api"
        SEARCH = "search"
        TOOL = "tool"

    class Source(models.TextChoices):
        SYSTEM = "system"
        CUSTOM = "custom"

    kind = models.CharField(max_length=16, choices=Kind.choices, db_index=True)
    name = models.CharField(max_length=128)
    company = models.CharField(max_length=64)
    key = models.CharField(max_length=512, blank=True, default="")
    request_url = models.CharField(max_length=512)
    is_hidden = models.BooleanField(default=False)
    is_using = models.BooleanField(default=False)
    capability_class = models.CharField(max_length=64, blank=True, default="")
    help = models.CharField(max_length=255, blank=True, default="")
    privacy_policy_url = models.CharField(max_length=512, blank=True, default="")
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.SYSTEM)
    position = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "position", "company", "name"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "company", "name"], name="uniq_ai_provider_key_kind_company_name"),
        ]

    def __str__(self):
        return f"{self.kind}:{self.company}:{self.name}"


class AIModelCatalog(models.Model):
    class Source(models.TextChoices):
        SYSTEM = "system"
        CUSTOM = "custom"

    name = models.CharField(max_length=128, unique=True)
    display_name = models.CharField(max_length=128)
    position = models.IntegerField(default=0, db_index=True)
    company = models.CharField(max_length=64)
    is_hidden = models.BooleanField(default=False)
    supports_search = models.BooleanField(default=False)
    supports_multimodal = models.BooleanField(default=False)
    supports_reasoning = models.BooleanField(default=False)
    supports_tool_use = models.BooleanField(default=False)
    supports_voice_gen = models.BooleanField(default=False)
    supports_image_gen = models.BooleanField(default=False)
    price_tier = models.PositiveSmallIntegerField(default=0)
    supports_text = models.BooleanField(default=True)
    reasoning_controllable = models.BooleanField(default=False)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.SYSTEM)
    is_active = models.BooleanField(default=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_tier__gte=0) & models.Q(price_tier__lte=3),
                name="aimodelcatalog_price_tier_0_3",
            ),
        ]

    def __str__(self):
        return self.name


class AIBootstrapProfile(models.Model):
    key = models.CharField(max_length=32, unique=True, default="default")
    choose_embedding_model = models.CharField(max_length=128, blank=True, default="")
    optimization_text_model = models.CharField(max_length=128, blank=True, default="")
    optimization_visual_model = models.CharField(max_length=128, blank=True, default="")
    text_to_speech_model = models.CharField(max_length=128, blank=True, default="")
    use_knowledge = models.BooleanField(default=True)
    knowledge_count = models.IntegerField(default=5)
    knowledge_similarity = models.FloatField(default=0.75)
    use_search = models.BooleanField(default=True)
    bilingual_search = models.BooleanField(default=False)
    search_count = models.IntegerField(default=3)
    use_map = models.BooleanField(default=False)
    use_calendar = models.BooleanField(default=False)
    use_weather = models.BooleanField(default=False)
    use_canvas = models.BooleanField(default=False)
    use_code = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"bootstrap:{self.key}"


class TrialApplication(models.Model):
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

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trial_application")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NONE, db_index=True)
    grant_source = models.CharField(max_length=16, choices=GrantSource.choices, default=GrantSource.AUTO)
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"trial:{self.user_id}:{self.status}"

    def is_active_trial(self) -> bool:
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at is None:
            return False
        return self.expires_at > timezone.now()


class TrialModelPolicy(models.Model):
    key = models.CharField(max_length=32, unique=True, default="default")
    name = models.CharField(max_length=64, default="Default Trial Policy")
    description = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"trial-policy:{self.key}"


class TrialModelPolicyItem(models.Model):
    policy = models.ForeignKey(TrialModelPolicy, on_delete=models.CASCADE, related_name="items")
    scenario = models.CharField(max_length=64, choices=AIScenarioConfig.Scenario.choices)
    model = models.ForeignKey("ai_config.AIModelCatalog", on_delete=models.PROTECT, related_name="trial_policy_items")
    temperature = models.FloatField(default=0.2)
    max_tokens = models.IntegerField(default=2048)
    position = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "scenario", "model__name"]
        constraints = [
            models.UniqueConstraint(fields=["policy", "scenario"], name="uniq_trial_model_policy_scenario"),
        ]

    def __str__(self):
        return f"{self.policy.key}:{self.scenario}:{self.model.name}"
