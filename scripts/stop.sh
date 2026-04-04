#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$BASE_DIR/run"

stop_by_pid_file() {
  local pid_file="$1"
  local name="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "$name not running (no pid file)"
    return
  fi

  local pid
  pid="$(cat "$pid_file" || true)"
  if [[ -z "$pid" ]]; then
    rm -f "$pid_file"
    echo "$name pid file empty, cleaned"
    return
  fi

  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.2
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "stopped $name (pid=$pid)"
  else
    echo "$name process not found, cleaning pid file"
  fi
  rm -f "$pid_file"
}

stop_by_pid_file "$RUN_DIR/celery_beat.pid" "celery_beat"
stop_by_pid_file "$RUN_DIR/celery_worker.pid" "celery_worker"
stop_by_pid_file "$RUN_DIR/django.pid" "django"

echo "all services stopped"
