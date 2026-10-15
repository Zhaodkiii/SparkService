#!/usr/bin/env bash
set -euo pipefail

# 日志清理脚本：
# 删除 LOG_ROOT 下超过 LOG_RETENTION_DAYS 天的日期目录和旧轮转文件。

BASE="${SPARK_BASE:-/root/2026}"
LOG_ROOT="${LOG_ROOT:-$BASE/shared/logs}"
RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"

if [[ ! -d "$LOG_ROOT" ]]; then
  echo "==> 日志目录不存在，跳过清理：$LOG_ROOT"
  exit 0
fi

echo "==> 清理 $RETENTION_DAYS 天前的日志：$LOG_ROOT"
find "$LOG_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION_DAYS" -print -exec rm -rf {} +
find "$LOG_ROOT" -type f \( -name "*.log.*" -o -name "*.stdout.log.*" -o -name "*.stderr.log.*" \) -mtime "+$RETENTION_DAYS" -delete
