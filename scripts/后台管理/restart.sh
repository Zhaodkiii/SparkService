#!/usr/bin/env bash
# 一键重启：先停止后端/前端，再重新启动

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

ensure_dirs
require_prereqs

echo "正在重启后台管理本地环境 ..."
stop_all
sleep 1
start_backend
start_frontend
print_status

echo "重启完成。"
