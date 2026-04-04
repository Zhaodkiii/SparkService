from django.db import models


class AIScenarioConfig(models.Model):
    class Scenario(models.TextChoices):
        CHAT = "chat"
        MEDICAL_EXTRACTION = "medical_extraction"
        EMBEDDING = "embedding"

    scenario = models.CharField(max_length=64, choices=Scenario.choices, unique=True)
    endpoint = models.CharField(max_length=512)
    model = models.CharField(max_length=128)
    api_key = models.CharField(max_length=512, blank=True, default="")
    temperature = models.FloatField(default=0.2)
    max_tokens = models.IntegerField(default=2048)
    is_active = models.BooleanField(default=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scenario"]

    def __str__(self):
        return f"{self.scenario}:{self.model}"


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
    class Identity(models.TextChoices):
        MODEL = "model"
        AGENT = "agent"

    class Source(models.TextChoices):
        SYSTEM = "system"
        CUSTOM = "custom"

    name = models.CharField(max_length=128, unique=True)
    display_name = models.CharField(max_length=128)
    identity = models.CharField(max_length=16, choices=Identity.choices, default=Identity.MODEL)
    position = models.IntegerField(default=0, db_index=True)
    company = models.CharField(max_length=64)
    is_hidden = models.BooleanField(default=False)
    supports_search = models.BooleanField(default=False)
    supports_multimodal = models.BooleanField(default=False)
    supports_reasoning = models.BooleanField(default=False)
    supports_tool_use = models.BooleanField(default=False)
    supports_voice_gen = models.BooleanField(default=False)
    supports_image_gen = models.BooleanField(default=False)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.SYSTEM)
    is_active = models.BooleanField(default=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "name"]

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
