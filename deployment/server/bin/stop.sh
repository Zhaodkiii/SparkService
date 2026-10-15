#!/usr/bin/env bash
set -euo pipefail
cd "${SPARK_BASE:-/root/2026}"
docker compose --env-file .deploy.env stop frontend celery_beat celery_worker web
