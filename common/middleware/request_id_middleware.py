import uuid

from common.request_context import request_id_var


class RequestIdMiddleware:
    """
    Attach a request correlation id to every request.
    This id is also injected into Celery task logs where possible.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(rid)
        request.request_id = rid
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = rid
            return response
        finally:
            request_id_var.reset(token)
