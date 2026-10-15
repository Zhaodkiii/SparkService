#!/usr/bin/env bash
# 一键启动：SparkService 后端 (2026) + backoffice-web (6018)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

ensure_dirs
require_prereqs

echo "正在启动 SparkService 本地开发环境 ..."
start_backend
start_frontend
print_status

echo "日志：$BACKEND_LOG 和 $FRONTEND_LOG"
echo "重启: $SCRIPT_DIR/restart.sh"
