from django.urls import path

from file_manager.views import (
    FileRegistrationView,
    ManagedFileBusinessUpdateView,
    ManagedFileDeleteView,
    ManagedFileDownloadURLView,
    ManagedFileListView,
    ManagedFilePreviewView,
)

urlpatterns = [
    path("", ManagedFileListView.as_view(), name="managed-file-list"),
    path("register/", FileRegistrationView.as_view(), name="managed-file-register"),
    path("business/update/", ManagedFileBusinessUpdateView.as_view(), name="managed-file-business-update"),
    path("<int:file_id>/preview/", ManagedFilePreviewView.as_view(), name="managed-file-preview"),
    path("<int:file_id>/download-url/", ManagedFileDownloadURLView.as_view(), name="managed-file-download-url"),
    path("<int:file_id>/", ManagedFileDeleteView.as_view(), name="managed-file-delete"),
]
