from django.urls import path

from file_manager.views import (
    ManagedFileBusinessUpdateView,
    ManagedFileDeleteView,
    ManagedFileDownloadView,
    ManagedFileListView,
    ManagedFileUploadView,
)

urlpatterns = [
    path("", ManagedFileListView.as_view(), name="managed-file-list"),
    path("upload/", ManagedFileUploadView.as_view(), name="managed-file-upload"),
    path("business/update/", ManagedFileBusinessUpdateView.as_view(), name="managed-file-business-update"),
    path("<int:file_id>/download/", ManagedFileDownloadView.as_view(), name="managed-file-download"),
    path("<int:file_id>/", ManagedFileDeleteView.as_view(), name="managed-file-delete"),
]
