#!/usr/bin/env bash
# 停止 SparkService 本地开发环境（后端 + 管理前端 + 分享前端）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

ensure_dirs

echo "正在停止 SparkService 本地开发环境 ..."
stop_all
print_status
echo "已停止。"
