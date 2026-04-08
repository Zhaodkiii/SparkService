from django.urls import path

from file_manager.oss_sts_views import OCRSTSCredentialsAPIView, STSCredentialsAPIView

urlpatterns = [
    path("sts/credentials/", STSCredentialsAPIView.as_view(), name="oss-sts-credentials"),
    path(
        "ocr/sts/credentials/",
        OCRSTSCredentialsAPIView.as_view(),
        name="oss-ocr-sts-credentials",
    ),
]
