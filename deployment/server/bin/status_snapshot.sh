#!/usr/bin/env bash
set -euo pipefail
cd "${SPARK_BASE:-/root/2026}"
readlink current
docker compose --env-file .deploy.env ps
df -h .
