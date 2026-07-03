#!/usr/bin/env bash
# 后台管理本地开发：公共路径与启停函数

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPARK_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKOFFICE_WEB="$SPARK_ROOT/backoffice-web"
SHARE_WEB="$SPARK_ROOT/share-web"
VENV_PYTHON="$SPARK_ROOT/.venv/bin/python"
PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/logs"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-2026}"
FRONTEND_PORT="${FRONTEND_PORT:-6018}"
SHARE_WEB_PORT="${SHARE_WEB_PORT:-1998}"

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
SHARE_WEB_PID_FILE="$PID_DIR/share-web.pid"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
SHARE_WEB_LOG="$LOG_DIR/share-web.log"

ensure_dirs() {
  mkdir -p "$PID_DIR" "$LOG_DIR"
}

require_prereqs() {
  if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "错误: 未找到 Python 虚拟环境: $VENV_PYTHON"
    echo "请在 SparkService 目录执行: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
  fi
  if [[ ! -f "$SPARK_ROOT/manage.py" ]]; then
    echo "错误: 未找到 manage.py: $SPARK_ROOT/manage.py"
    exit 1
  fi
  if [[ ! -d "$BACKOFFICE_WEB" ]]; then
    echo "错误: 未找到前端目录: $BACKOFFICE_WEB"
    exit 1
  fi
  if [[ ! -d "$SHARE_WEB" ]]; then
    echo "错误: 未找到分享前端目录: $SHARE_WEB"
    exit 1
  fi
  if ! command -v pnpm >/dev/null 2>&1; then
    echo "错误: 未找到 pnpm，请先安装: https://pnpm.io/installation"
    exit 1
  fi
}

port_pids() {
  local port="$1"
  lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true
}

is_pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    tr -d '[:space:]' <"$file"
  fi
}

stop_pid_file() {
  local name="$1"
  local file="$2"
  local pid
  pid="$(read_pid_file "$file")"
  if is_pid_alive "$pid"; then
    echo "停止 ${name} (pid=${pid}) ..."
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      is_pid_alive "$pid" || break
      sleep 0.25
    done
    if is_pid_alive "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$file"
}

stop_port() {
  local name="$1"
  local port="$2"
  local pids
  pids="$(port_pids "$port")"
  if [[ -n "$pids" ]]; then
    echo "释放端口 ${port} (${name}) ..."
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 0.5
    pids="$(port_pids "$port")"
    if [[ -n "$pids" ]]; then
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

stop_backend() {
  stop_pid_file "Django 后端" "$BACKEND_PID_FILE"
  stop_port "Django 后端" "$BACKEND_PORT"
  pkill -f "${SPARK_ROOT}/manage.py runserver" 2>/dev/null || true
}

stop_frontend() {
  stop_pid_file "Vite 前端" "$FRONTEND_PID_FILE"
  stop_port "Vite 前端" "$FRONTEND_PORT"
  pkill -f "vite.*${BACKOFFICE_WEB}" 2>/dev/null || true
}

stop_share_web() {
  stop_pid_file "分享前端" "$SHARE_WEB_PID_FILE"
  stop_port "分享前端" "$SHARE_WEB_PORT"
  pkill -f "vite.*${SHARE_WEB}" 2>/dev/null || true
}

stop_all() {
  stop_share_web
  stop_frontend
  stop_backend
}

backend_listening() {
  [[ -n "$(port_pids "$BACKEND_PORT")" ]]
}

frontend_listening() {
  [[ -n "$(port_pids "$FRONTEND_PORT")" ]]
}

share_web_listening() {
  [[ -n "$(port_pids "$SHARE_WEB_PORT")" ]]
}

start_backend() {
  if backend_listening; then
    echo "Django 后端已在运行: http://${BACKEND_HOST}:${BACKEND_PORT}/"
    return 0
  fi
  echo "启动 Django 后端 -> http://${BACKEND_HOST}:${BACKEND_PORT}/"
  (
    cd "$SPARK_ROOT"
    export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-SparkService.settings}"
    nohup "$VENV_PYTHON" manage.py runserver "${BACKEND_HOST}:${BACKEND_PORT}" >>"$BACKEND_LOG" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )
  for _ in $(seq 1 40); do
    backend_listening && break
    sleep 0.25
  done
  if ! backend_listening; then
    echo "后端启动可能失败，请查看日志: $BACKEND_LOG"
    tail -n 30 "$BACKEND_LOG" || true
    exit 1
  fi
}

start_frontend() {
  if frontend_listening; then
    echo "后台管理前端已在运行: http://localhost:${FRONTEND_PORT}/"
    return 0
  fi
  if [[ ! -d "$BACKOFFICE_WEB/node_modules" ]]; then
    echo "首次启动：安装前端依赖 (pnpm install) ..."
    (cd "$BACKOFFICE_WEB" && pnpm install)
  fi
  echo "启动 Vite 前端 -> http://localhost:${FRONTEND_PORT}/"
  (
    cd "$BACKOFFICE_WEB"
    nohup pnpm dev >>"$FRONTEND_LOG" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )
  for _ in $(seq 1 40); do
    frontend_listening && break
    sleep 0.25
  done
  if ! frontend_listening; then
    echo "前端启动可能失败，请查看日志: $FRONTEND_LOG"
    tail -n 30 "$FRONTEND_LOG" || true
    exit 1
  fi
}

start_share_web() {
  if share_web_listening; then
    echo "分享前端已在运行: http://localhost:${SHARE_WEB_PORT}/"
    return 0
  fi
  if [[ ! -d "$SHARE_WEB/node_modules" ]]; then
    echo "首次启动：安装分享前端依赖 (pnpm install) ..."
    (cd "$SHARE_WEB" && pnpm install)
  fi
  echo "启动分享前端 -> http://localhost:${SHARE_WEB_PORT}/"
  (
    cd "$SHARE_WEB"
    nohup pnpm dev >>"$SHARE_WEB_LOG" 2>&1 &
    echo $! >"$SHARE_WEB_PID_FILE"
  )
  for _ in $(seq 1 40); do
    share_web_listening && break
    sleep 0.25
  done
  if ! share_web_listening; then
    echo "分享前端启动可能失败，请查看日志: $SHARE_WEB_LOG"
    tail -n 30 "$SHARE_WEB_LOG" || true
    exit 1
  fi
}

print_status() {
  echo ""
  echo "======== SparkService 本地开发服务 ========"
  if backend_listening; then
    echo "后端 API : http://${BACKEND_HOST}:${BACKEND_PORT}/"
  else
    echo "后端 API : 未运行"
  fi
  if frontend_listening; then
    echo "管理前端 : http://localhost:${FRONTEND_PORT}/"
  else
    echo "管理前端 : 未运行"
  fi
  if share_web_listening; then
    echo "分享前端 : http://localhost:${SHARE_WEB_PORT}/"
  else
    echo "分享前端 : 未运行"
  fi
  echo "后端日志 : $BACKEND_LOG"
  echo "管理日志 : $FRONTEND_LOG"
  echo "分享日志 : $SHARE_WEB_LOG"
  echo "=================================="
  echo ""
}
