from django.urls import path

from subscriptions.views import RevenueCatSubscriptionSyncView, SubscriptionMeView


urlpatterns = [
    path("me/", SubscriptionMeView.as_view(), name="subscription_me"),
    path("revenuecat/sync/", RevenueCatSubscriptionSyncView.as_view(), name="revenuecat_subscription_sync"),
]
