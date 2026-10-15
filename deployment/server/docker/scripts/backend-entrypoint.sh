#!/usr/bin/env bash
set -euo pipefail

# 容器启动前等待基础依赖可连接，避免 Django/Celery 抢跑。

wait_tcp() {
  local host="$1"
  local port="$2"
  local name="$3"
  local timeout="${4:-60}"

  echo "==> 等待 $name：$host:$port"
  for _ in $(seq 1 "$timeout"); do
    if nc -z "$host" "$port" >/dev/null 2>&1; then
      echo "==> $name 已就绪"
      return 0
    fi
    sleep 1
  done

  echo "❌ $name 等待超时：$host:$port" >&2
  exit 1
}

if [[ -n "${DB_HOST:-}" && -n "${DB_PORT:-}" ]]; then
  wait_tcp "$DB_HOST" "$DB_PORT" "MySQL"
fi

if [[ -n "${REDIS_HOST:-redis}" && -n "${REDIS_PORT:-6379}" ]]; then
  wait_tcp "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}" "Redis"
fi

exec "$@"

