from django.urls import path

from ai_config.views import AIBootstrapConfigView

urlpatterns = [
    path("config/bootstrap/", AIBootstrapConfigView.as_view(), name="ai_config_bootstrap"),
]
