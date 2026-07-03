#!/usr/bin/env bash
# 一键重启：先停止后端/管理前端/分享前端，再重新启动

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

ensure_dirs
require_prereqs

echo "正在重启 SparkService 本地开发环境 ..."
stop_all
sleep 1
start_backend
start_frontend
start_share_web
print_status

echo "重启完成。"
