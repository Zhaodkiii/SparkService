import contextvars

# Used to correlate API requests with Celery tasks and structured logs.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

