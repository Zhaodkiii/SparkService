# SparkService Log Standard

## Directory
- Runtime directory: `/Users/dream/Downloads/Reference/SparkService/logs`
- Main files:
- `app.log`: business/application logs
- `access.log`: request access logs
- `celery.log`: celery worker/beat logs
- `accounts.flow` events are written to both `access.log` and `app.log` for end-to-end business tracing

## Rotation
- Handler: `TimedRotatingFileHandler`
- Rotate: midnight
- Retention: `LOG_BACKUP_COUNT` (default `14`)

## API IO Policy
- API request/response headers and bodies are logged in raw form (no redaction).
- This is intended for deep debugging in controlled environments.
- API inbound/outbound logs are written into `app.log` by default (logger: `accounts.api_io`).
- You can additionally mirror API IO logs to `access.log` via `LOG_API_IO_TO_ACCESS=true`.
- You can temporarily disable API IO payload logs via `LOG_API_IO_ENABLED=false`.
