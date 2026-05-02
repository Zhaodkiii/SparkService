from django.urls import path

from app_version.views import UpdateActionAPI, VersionCheckAPI


urlpatterns = [
    path("check/", VersionCheckAPI.as_view(), name="app-version-check"),
    path("action/", UpdateActionAPI.as_view(), name="app-version-action"),
]
