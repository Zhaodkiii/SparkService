#!/usr/bin/env bash
# 停止后台管理本地环境（后端 + 前端）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

ensure_dirs

echo "正在停止后台管理本地环境 ..."
stop_all
print_status
echo "已停止。"
