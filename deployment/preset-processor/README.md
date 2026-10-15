# Preset resource processor

Deploy this container on a dedicated cn-beijing compute instance with OSS internal connectivity, never on the low-bandwidth API host. Build using the repository root as Docker build context. Give it >= 6 GiB temporary disk, resource limits and outbound HTTPS to the control API. Current implementation uses a dedicated polling container, not an FC invocation endpoint.

Required environment: PRESET_CONTROL_URL, DIARY_PRESETS_PROCESSOR_TOKEN (same random secret as API), ALIYUN_ACCESS_KEY_ID, ALIYUN_ACCESS_KEY_SECRET, ALIYUN_OSS_BUCKET. Optional: PRESET_WORKER_OSS_ENDPOINT (defaults Beijing internal), DIARY_PRESETS_OSS_PREFIX.

Use a dedicated worker RAM identity permitted to read staging and write immutable blobs only. Do not use browser upload credentials. API identity additionally needs AssumeRole on DIARY_PRESETS_UPLOAD_ROLE_ARN; that role must permit only scoped staging multipart uploads. Configure OSS CORS for the actual backoffice origin.

This is an independent deployment: no existing server startup script enables this worker. Set a container restart policy. Jobs use 30-minute leases; work exceeding that time is rejected and reclaimed. Tune package limits and execution resources accordingly. Failed jobs remain inspectable through the upload API; do not manually publish unvalidated input.
