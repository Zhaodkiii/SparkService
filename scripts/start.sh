#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_TEMPLATE_DIR="${SERVER_TEMPLATE_DIR:-$(cd "$BASE_DIR/.." && pwd)/2026}"

SPARK_BASE="${SPARK_BASE:-$BASE_DIR}" \
SPARK_APP_DIR="${SPARK_APP_DIR:-$BASE_DIR}" \
exec "$SERVER_TEMPLATE_DIR/bin/start.sh" "$@"
