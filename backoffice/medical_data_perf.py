from __future__ import annotations

import logging
import time
from functools import wraps

from django.utils import timezone
from rest_framework import status

from common.response import error_response, success_response

logger = logging.getLogger(__name__)

MAX_PAGE = 100
MAX_PAGE_NUMBER = 500
QUERY_BUDGET_SECONDS = 8.0


def medical_data_meta(*, duration_ms: int, cache_hit: bool = False, stats_status: str = "ready") -> dict:
    return {
        "duration_ms": duration_ms,
        "cache_hit": cache_hit,
        "stats_status": stats_status,
        "generated_at": timezone.now().isoformat(),
    }


def paginate_params(request, default_page_size: int = 20) -> tuple[int, int]:
    page = max(int(request.query_params.get("page", "1")), 1)
    page_size = min(max(int(request.query_params.get("page_size", str(default_page_size))), 1), MAX_PAGE)
    if page > MAX_PAGE_NUMBER:
        raise ValueError("page_out_of_range")
    return page, page_size


def with_medical_data_perf(view_method):
    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        start = time.perf_counter()
        request_id = getattr(request, "request_id", "") or ""
        path = request.path
        admin_id = getattr(request.user, "id", None)
        try:
            response = view_method(self, request, *args, **kwargs)
            duration_ms = int((time.perf_counter() - start) * 1000)
            if duration_ms > int(QUERY_BUDGET_SECONDS * 1000):
                logger.warning(
                    "medical_data slow request",
                    extra={
                        "path": path,
                        "duration_ms": duration_ms,
                        "admin_id": admin_id,
                        "request_id": request_id,
                        "query_params": dict(request.query_params),
                    },
                )
            else:
                logger.info(
                    "medical_data request",
                    extra={
                        "path": path,
                        "duration_ms": duration_ms,
                        "admin_id": admin_id,
                        "request_id": request_id,
                    },
                )
            if hasattr(response, "data") and isinstance(response.data, dict):
                data = response.data.get("data")
                if isinstance(data, dict) and "meta" not in data:
                    data["meta"] = medical_data_meta(duration_ms=duration_ms)
            return response
        except ValueError as exc:
            if str(exc) == "page_out_of_range":
                duration_ms = int((time.perf_counter() - start) * 1000)
                return error_response(
                    msg="page_out_of_range",
                    code=40002,
                    status_code=status.HTTP_400_BAD_REQUEST,
                    data={
                        "detail": f"页码不能超过 {MAX_PAGE_NUMBER}",
                        "request_id": request_id,
                        "meta": medical_data_meta(duration_ms=duration_ms),
                    },
                )
            raise
        except Exception:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "medical_data request failed",
                extra={"path": path, "duration_ms": duration_ms, "admin_id": admin_id, "request_id": request_id},
            )
            raise

    return wrapper


def success_with_meta(payload: dict, *, duration_ms: int, cache_hit: bool = False, stats_status: str = "ready"):
    payload = dict(payload)
    payload["meta"] = medical_data_meta(duration_ms=duration_ms, cache_hit=cache_hit, stats_status=stats_status)
    return success_response(payload, msg="success", code=0, status_code=status.HTTP_200_OK)
