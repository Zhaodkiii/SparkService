from django.urls import path

from file_manager.public_views import PublicImageUploadView

urlpatterns = [
    path("images/", PublicImageUploadView.as_view(), name="public-image-upload"),
]
