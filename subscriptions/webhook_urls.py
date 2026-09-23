from django.urls import path

from subscriptions.views import RevenueCatWebhookView


urlpatterns = [path("webhook/", RevenueCatWebhookView.as_view(), name="revenuecat_webhook")]
