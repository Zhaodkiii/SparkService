import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import error_response, success_response
from file_manager.sts_utils import get_sts_credentials

logger = logging.getLogger(__name__)


def _sts_payload():
    return get_sts_credentials()


class STSCredentialsAPIView(APIView):
    """GET /api/v1/oss/sts/credentials/ — 通用 OSS STS（与 Health 路径语义对齐）。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            data = _sts_payload()
            logger.info("OSS STS 签发成功 user_id=%s", request.user.id)
            return success_response(data, msg="success", code=0, status_code=status.HTTP_200_OK)
        except ValueError as e:
            logger.error("OSS STS 配置错误: %s", e)
            return error_response(
                msg=str(e),
                code=5001,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except RuntimeError as e:
            logger.error("OSS STS 失败: %s", e)
            return error_response(
                msg=str(e),
                code=5002,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class OCRSTSCredentialsAPIView(APIView):
    """GET /api/v1/oss/ocr/sts/credentials/ — SparkClient OCR 已约定路径；凭证与 OSS STS 相同。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            data = _sts_payload()
            logger.info("OCR STS 签发成功 user_id=%s", request.user.id)
            return success_response(data, msg="success", code=0, status_code=status.HTTP_200_OK)
        except ValueError as e:
            logger.error("OCR STS 配置错误: %s", e)
            return error_response(
                msg=str(e),
                code=5001,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except RuntimeError as e:
            logger.error("OCR STS 失败: %s", e)
            return error_response(
                msg=str(e),
                code=5002,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
