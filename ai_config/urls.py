from django.urls import path

from ai_config.views import AIBootstrapConfigView, TrialApplyView, TrialStatusView, AIProviderConnectionTestView, ScenarioToolPreviewView

urlpatterns = [
    path("config/bootstrap/", AIBootstrapConfigView.as_view(), name="ai_config_bootstrap"),
    path("config/scenarios/<str:scenario_key>/tools/", ScenarioToolPreviewView.as_view(), name="ai_config_scenario_tools"),
    path("trial/status/", TrialStatusView.as_view(), name="ai_trial_status"),
    path("trial/apply/", TrialApplyView.as_view(), name="ai_trial_apply"),
    path("providers/test-connection/", AIProviderConnectionTestView.as_view(), name="ai_provider_test_connection"),
]
