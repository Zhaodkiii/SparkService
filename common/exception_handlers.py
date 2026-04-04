from common.exceptions import APIError

from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


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
        return Response(
            {"code": exc.code, "msg": exc.msg, "data": exc.details if exc.details is not None else error_data},
            status=exc.status_code,
        )

    return Response(
        {"code": -1, "msg": "Internal Server Error", "data": error_data},
        status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
