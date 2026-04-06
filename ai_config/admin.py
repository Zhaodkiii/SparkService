from django.contrib import admin

from ai_config.models import (
    AIBootstrapProfile,
    AIModelCatalog,
    AIProviderKeyConfig,
    AIScenarioModelBinding,
    TrialApplication,
    TrialModelPolicy,
    TrialModelPolicyItem,
)


@admin.register(AIScenarioModelBinding)
class AIScenarioModelBindingAdmin(admin.ModelAdmin):
    list_display = ("scenario", "identity", "model", "is_default", "is_active", "position", "updated_at")
    list_filter = ("scenario", "is_active", "is_default")
    search_fields = ("scenario", "model__name", "model__display_name")
    ordering = ("scenario", "position")


@admin.register(AIProviderKeyConfig)
class AIProviderKeyConfigAdmin(admin.ModelAdmin):
    list_display = ("kind", "name", "company", "is_using", "is_active", "position", "updated_at")
    list_filter = ("kind", "is_using", "is_active", "source")
    search_fields = ("name", "company", "request_url", "privacy_policy_url")


@admin.register(AIModelCatalog)
class AIModelCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "display_name", "company", "position", "is_active", "updated_at")
    list_filter = ("company", "source", "is_active")
    search_fields = ("name", "display_name")


@admin.register(AIBootstrapProfile)
class AIBootstrapProfileAdmin(admin.ModelAdmin):
    list_display = ("key", "choose_embedding_model", "optimization_text_model", "updated_at")
    search_fields = ("key", "choose_embedding_model", "optimization_text_model")


@admin.register(TrialApplication)
class TrialApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "grant_source", "started_at", "expires_at", "updated_at")
    list_filter = ("status", "grant_source")
    search_fields = ("user__username", "user__email", "note")


class TrialModelPolicyItemInline(admin.TabularInline):
    model = TrialModelPolicyItem
    extra = 1


@admin.register(TrialModelPolicy)
class TrialModelPolicyAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("key", "name", "description")
    inlines = [TrialModelPolicyItemInline]
