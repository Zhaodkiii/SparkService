#!/usr/bin/env bash
set -euo pipefail
cd "${SPARK_BASE:-/root/2026}"
docker compose --env-file .deploy.env restart web celery_worker celery_beat frontend
