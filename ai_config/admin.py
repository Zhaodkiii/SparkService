from django.contrib import admin

from ai_config.models import AIBootstrapProfile, AIModelCatalog, AIProviderKeyConfig, AIScenarioConfig


@admin.register(AIScenarioConfig)
class AIScenarioConfigAdmin(admin.ModelAdmin):
    list_display = ("scenario", "model", "endpoint", "is_active", "updated_at")
    list_filter = ("scenario", "is_active")
    search_fields = ("scenario", "model", "endpoint")


@admin.register(AIProviderKeyConfig)
class AIProviderKeyConfigAdmin(admin.ModelAdmin):
    list_display = ("kind", "name", "company", "is_using", "is_active", "position", "updated_at")
    list_filter = ("kind", "is_using", "is_active", "source")
    search_fields = ("name", "company", "request_url")


@admin.register(AIModelCatalog)
class AIModelCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "display_name", "company", "position", "is_active", "updated_at")
    list_filter = ("identity", "company", "source", "is_active")
    search_fields = ("name", "display_name")


@admin.register(AIBootstrapProfile)
class AIBootstrapProfileAdmin(admin.ModelAdmin):
    list_display = ("key", "choose_embedding_model", "optimization_text_model", "updated_at")
    search_fields = ("key", "choose_embedding_model", "optimization_text_model")
