from django.urls import path

from file_manager.chat_image_views import ChatImageUploadSessionCompleteView, ChatImageUploadSessionView
from file_manager.oss_sts_views import OCRSTSCredentialsAPIView, STSCredentialsAPIView

urlpatterns = [
    path("sts/credentials/", STSCredentialsAPIView.as_view(), name="oss-sts-credentials"),
    path(
        "ocr/sts/credentials/",
        OCRSTSCredentialsAPIView.as_view(),
        name="oss-ocr-sts-credentials",
    ),
    path(
        "chat-images/upload-sessions/",
        ChatImageUploadSessionView.as_view(),
        name="oss-chat-image-upload-session",
    ),
    path(
        "chat-images/upload-sessions/<str:session_id>/complete/",
        ChatImageUploadSessionCompleteView.as_view(),
        name="oss-chat-image-upload-complete",
    ),
]
