# SparkService Log Standard

## Directory
- Runtime directory: `/Users/dream/Downloads/Reference/SparkService/logs`
- Main files:
- `app.log`: business/application logs
- `access.log`: per-request summary (method/path/status/duration)
- `access_api_io.log`: accounts API request/response headers and bodies (same policy as `medical_api_io.log`)
- `celery.log`: celery worker/beat logs
- `accounts.flow` events are written to both `access.log` and `app.log` for end-to-end business tracing

## Rotation
- Handler: `TimedRotatingFileHandler`
- Rotate: midnight
- Retention: `LOG_BACKUP_COUNT` (default `14`)

## API IO Policy
- API request/response headers and bodies are logged in raw form (no redaction).
- This is intended for deep debugging in controlled environments.
- API inbound/outbound logs (`accounts.api_io`) are written to `access_api_io.log` (and console), same layout as `medical.api_io` → `medical_api_io.log`.
- You can temporarily disable API IO payload logs via `LOG_API_IO_ENABLED=false`.
