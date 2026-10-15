#!/usr/bin/env bash
# TravelDiary 本地后端、管理后台与账号异步任务。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPARK_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export VENV_PYTHON="${VENV_PYTHON:-$SPARK_ROOT/.venv/bin/python}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-SparkService.settings}"
export BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
export BACKEND_PORT="${BACKEND_PORT:-2026}"
export FRONTEND_HOST="${FRONTEND_HOST:-localhost}"
export FRONTEND_PORT="${FRONTEND_PORT:-6018}"
START_FRONTEND=1
START_ASYNC=1
CHECK_ONLY=0

parse_options() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-frontend) START_FRONTEND=0 ;;
      --no-async) START_ASYNC=0 ;;
      --check) CHECK_ONLY=1 ;;
      --help|-h)
        echo "用法: $0 [--no-frontend] [--no-async] [--check]"
        echo "默认启动 API、管理后台、Celery Worker 与 Beat。Redis/数据库需预先运行。"
        echo "--check 仅检查环境、数据库迁移状态与 Redis，不启动服务。"
        exit 0 ;;
      *) echo "未知参数: $1" >&2; exit 2 ;;
    esac
    shift
  done
}

runtime() { "$VENV_PYTHON" "$SPARK_ROOT/scripts/runtime.py" "$@"; }

require_prereqs() {
  [[ -x "$VENV_PYTHON" ]] || { echo "请先创建 .venv 并安装 requirements.txt" >&2; exit 1; }
  if [[ "$START_FRONTEND" == 1 ]]; then
    command -v node >/dev/null || { echo "请先安装 Node.js" >&2; exit 1; }
    [[ -f "$SPARK_ROOT/backoffice-web/node_modules/vite/bin/vite.js" ]] || {
      echo "请先在 backoffice-web 执行 pnpm install --frozen-lockfile" >&2; exit 1;
    }
  fi
  (cd "$SPARK_ROOT" && "$VENV_PYTHON" manage.py check && "$VENV_PYTHON" manage.py migrate --check) || {
    echo "环境检查失败；如有未应用迁移，请先执行 python manage.py migrate。" >&2; exit 1;
  }
  if [[ "$START_ASYNC" == 1 ]]; then
    runtime check-broker || { echo "请先启动配置的 Redis，或使用 --no-async。" >&2; exit 1; }
  fi
}

start_all() {
  runtime start backend
  if [[ "$START_ASYNC" == 1 ]]; then
    runtime start celery_worker
    runtime start celery_beat
  fi
  if [[ "$START_FRONTEND" == 1 ]]; then runtime start frontend; fi
}

stop_all() {
  runtime stop frontend
  runtime stop celery_beat
  runtime stop celery_worker
  runtime stop backend
}

print_status() {
  runtime status
  echo "API: http://${BACKEND_HOST}:${BACKEND_PORT}/"
  echo "管理后台: http://${FRONTEND_HOST}:${FRONTEND_PORT}/"
  echo "日志: $SPARK_ROOT/logs/<服务名>.stdout.log / .stderr.log"
}
