#!/usr/bin/env bash
# 一键启动：SparkService 后端 (2026) + backoffice-web (6018) + share-web (1998)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

ensure_dirs
require_prereqs

echo "正在启动 SparkService 本地开发环境 ..."
start_backend
start_frontend
start_share_web
print_status

echo "提示: 进程在后台运行；查看日志可用 tail -f \"$BACKEND_LOG\"、\"$FRONTEND_LOG\" 或 \"$SHARE_WEB_LOG\""
echo "重启: $SCRIPT_DIR/restart.sh"
