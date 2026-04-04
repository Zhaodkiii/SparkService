#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$BASE_DIR/run"
LOG_DIR="$BASE_DIR/logs"
VENV_DIR="$BASE_DIR/.venv"

DJANGO_HOST="${DJANGO_HOST:-0.0.0.0}"
DJANGO_PORT="${DJANGO_PORT:-8000}"
CELERY_LOGLEVEL="${CELERY_LOGLEVEL:-INFO}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

if [[ -f "$VENV_DIR/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
fi

cd "$BASE_DIR"

start_if_not_running() {
  local pid_file="$1"
  local name="$2"
  shift 2
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$name already running (pid=$pid)"
      return
    fi
    rm -f "$pid_file"
  fi

  nohup "$@" >> "$LOG_DIR/${name}.stdout.log" 2>> "$LOG_DIR/${name}.stderr.log" &
  local new_pid=$!
  echo "$new_pid" > "$pid_file"
  echo "started $name (pid=$new_pid)"
}

start_if_not_running "$RUN_DIR/django.pid" "django" \
  python3 manage.py runasgi --host "${DJANGO_HOST}" --port "${DJANGO_PORT}"

start_if_not_running "$RUN_DIR/celery_worker.pid" "celery_worker" \
  celery -A SparkService worker --loglevel="$CELERY_LOGLEVEL"

start_if_not_running "$RUN_DIR/celery_beat.pid" "celery_beat" \
  celery -A SparkService beat --loglevel="$CELERY_LOGLEVEL"

echo "all services started"
