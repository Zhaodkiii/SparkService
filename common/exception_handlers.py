import logging

from common.exceptions import APIError

from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("django.request")


def api_exception_handler(exc, context):
    """
    Enforce a stable error schema for all DRF errors.
    """
    request = context.get("request") if isinstance(context, dict) else None
    request_id = getattr(request, "request_id", None)
    error_data = {"request_id": request_id} if request_id else None

    drf_response = drf_exception_handler(exc, context)
    if drf_response is not None:
        # Keep DRF status code; map message to schema.
        msg = getattr(exc, "detail", None) or str(exc)
        return Response({"code": -1, "msg": msg, "data": error_data}, status=drf_response.status_code)

    if isinstance(exc, APIError):
        payload = exc.details if exc.details is not None else error_data
        if isinstance(payload, dict) and request_id and "request_id" not in payload:
            payload = {**payload, "request_id": request_id}
        return Response(
            {"code": exc.code, "msg": exc.msg, "data": payload},
            status=exc.status_code,
        )

    # Unexpected exception: log full traceback so it appears in app logs.
    path = getattr(request, "path", "unknown")
    method = getattr(request, "method", "unknown")
    logger.exception(
        "Unhandled exception [request_id=%s] %s %s",
        request_id,
        method,
        path,
        exc_info=exc,
    )
    return Response(
        {"code": -1, "msg": "Internal Server Error", "data": error_data},
        status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
