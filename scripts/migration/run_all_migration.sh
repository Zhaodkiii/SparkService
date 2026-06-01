#!/usr/bin/env bash
# 按顺序一键执行 ZhaodkDream -> SparkService 全部分批迁移命令。
#
# 用法:
#   ./scripts/migration/run_all_migration.sh              # 正式迁移
#   ./scripts/migration/run_all_migration.sh --dry-run    # 试跑（不写新库）
#   ./scripts/migration/run_all_migration.sh --from 06      # 从第 6 步起执行
#   ./scripts/migration/run_all_migration.sh --from 06 --to 10
#   ./scripts/migration/run_all_migration.sh --stop-services     # 不询问，先停服务，结束后自动启动
#   ./scripts/migration/run_all_migration.sh --no-stop-services  # 不询问，不停服务
#   SKIP_RESET_DB=1 ./scripts/migration/run_all_migration.sh  # 跳过 scripts/migration/reset_db.sh
#
# 数据库配置已写死（本机迁移用）。修改连接信息请直接改下方常量。

set -euo pipefail
set -o pipefail

BASE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="$BASE_DIR/.venv"
LOG_DIR="$BASE_DIR/logs/migration"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/migration_${TIMESTAMP}.log"
ERROR_LOG="$BASE_DIR/scripts/migration/state/errors.log"

# ---------- 新库 sparkservice（Django manage.py 写入目标） ----------
DB_ENGINE="django.db.backends.mysql"
DB_HOST="127.0.0.1"
DB_PORT="3306"
DB_NAME="sparkservice"
DB_USER="root"
DB_PASSWORD="Zhao1029*"
DB_CONN_MAX_AGE="60"

# ---------- 旧库 ZhaodkDream（只读源） ----------
ZDK_OLD_DB_HOST="127.0.0.1"
ZDK_OLD_DB_PORT="3306"
ZDK_OLD_DB_NAME="ZhaodkDream"
ZDK_OLD_DB_USER="root"
ZDK_OLD_DB_PASSWORD="Zhao1029*"

DRY_RUN=0
FROM_STEP=0
TO_STEP=99
BATCH_SIZE=""
SKIP_RESET_DB="${SKIP_RESET_DB:-0}"
SERVICE_CONTROL="ask"
SERVICES_STOPPED_BY_MIGRATION=0
SERVICE_RESTORE_RUNNING=0
SERVICE_BASE="${MIGRATION_SERVICE_BASE:-}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-2026}"
AFFECTED_SERVICES=(web celery_worker celery_beat frontend)

fail() {
  echo "❌ $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: run_all_migration.sh [options]

Options:
  --dry-run           所有步骤加 --dry-run，不写新库
  --from N            从步骤 N 开始（0-18 或 99）
  --to N              到步骤 N 结束（默认 99）
  --batch-size N      传给各 migrate 命令的 --batch-size
  --stop-services     迁移前自动停止受影响服务，结束后自动启动
  --no-stop-services  迁移前不停止服务
  -h, --help          显示帮助

Steps:
  00 check  01 auth_users       02 account_profiles  03 social_identities
  04 trusted_devices  05 account_audit  06 members  07 medical_cases
  08 clinical_children  09 exam_reports  10 health_exams  11 prescriptions
  12 medication_plans  13 medication_records  14 files  15 ai_config
  16 chat  17 app_version  18 notifications  98 repair_client_extra  99 verify
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --from)
      FROM_STEP="${2:?missing value for --from}"
      shift 2
      ;;
    --to)
      TO_STEP="${2:?missing value for --to}"
      shift 2
      ;;
    --batch-size)
      BATCH_SIZE="${2:?missing value for --batch-size}"
      shift 2
      ;;
    --stop-services)
      SERVICE_CONTROL="yes"
      shift
      ;;
    --no-stop-services)
      SERVICE_CONTROL="no"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

mkdir -p "$LOG_DIR"
mkdir -p "$(dirname "$ERROR_LOG")"
: > "$ERROR_LOG"

if [[ -f "$VENV_DIR/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
fi

cd "$BASE_DIR"

export DB_ENGINE DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD DB_CONN_MAX_AGE
export ZDK_OLD_DB_HOST ZDK_OLD_DB_PORT ZDK_OLD_DB_NAME ZDK_OLD_DB_USER ZDK_OLD_DB_PASSWORD

ask_yes_no() {
  local prompt="$1"
  local answer

  if [[ ! -t 0 ]]; then
    echo "[service] 当前不是交互终端，无法询问。"
    return 1
  fi

  while true; do
    read -r -p "$prompt [y/N]: " answer
    case "$answer" in
      y|Y|yes|YES|Yes)
        return 0
        ;;
      ""|n|N|no|NO|No)
        return 1
        ;;
      *)
        echo "请输入 y 或 n"
        ;;
    esac
  done
}

resolve_service_base() {
  if [[ -n "$SERVICE_BASE" && -f "$SERVICE_BASE/docker-compose.yml" ]]; then
    return 0
  fi

  if [[ -f "/root/2026/docker-compose.yml" ]]; then
    SERVICE_BASE="/root/2026"
    return 0
  fi

  if [[ -f "$BASE_DIR/../2026/docker-compose.yml" ]]; then
    SERVICE_BASE="$(cd "$BASE_DIR/../2026" && pwd)"
    return 0
  fi

  if [[ -f "$BASE_DIR/docker-compose.yml" ]]; then
    SERVICE_BASE="$BASE_DIR"
    return 0
  fi

  return 1
}

compose_cmd() {
  resolve_service_base || true

  if [[ -n "$SERVICE_BASE" && -f "$SERVICE_BASE/.deploy.env" ]] && docker compose version >/dev/null 2>&1; then
    docker compose --env-file "$SERVICE_BASE/.deploy.env" -f "$SERVICE_BASE/docker-compose.yml" "$@"
  elif [[ -n "$SERVICE_BASE" && -f "$SERVICE_BASE/.deploy.env" ]] && command -v docker-compose >/dev/null 2>&1; then
    docker-compose --env-file "$SERVICE_BASE/.deploy.env" -f "$SERVICE_BASE/docker-compose.yml" "$@"
  elif docker_socket_service_cmd "$@"; then
    return 0
  else
    fail "[service] 当前环境没有可用的 docker compose 或 Docker socket，无法管理受影响服务。请在宿主机执行，或给迁移容器挂载 /var/run/docker.sock。"
  fi
}

docker_socket_available() {
  [[ -S /var/run/docker.sock ]] && command -v curl >/dev/null 2>&1
}

docker_container_name() {
  local service="$1"
  printf '%s-%s-1' "$COMPOSE_PROJECT_NAME" "$service"
}

docker_socket_request() {
  local method="$1"
  local path="$2"
  local code

  code="$(curl -sS -o /tmp/sparkservice_docker_api_body.$$ -w '%{http_code}' \
    --unix-socket /var/run/docker.sock \
    -X "$method" \
    "http://localhost$path" || true)"

  if [[ "$code" == "200" || "$code" == "204" || "$code" == "304" ]]; then
    rm -f /tmp/sparkservice_docker_api_body.$$
    return 0
  fi

  echo "[service] Docker API 请求失败：$method $path HTTP $code"
  if [[ -s /tmp/sparkservice_docker_api_body.$$ ]]; then
    sed 's/^/[service] Docker API: /' /tmp/sparkservice_docker_api_body.$$
  fi
  rm -f /tmp/sparkservice_docker_api_body.$$
  return 1
}

docker_socket_ps_one() {
  local service="$1"
  local name
  local body
  name="$(docker_container_name "$service")"

  body="$(curl -sS --unix-socket /var/run/docker.sock "http://localhost/containers/$name/json" || true)"
  BODY="$body" SERVICE="$service" NAME="$name" python - <<'PY'
import json
import os

service = os.environ["SERVICE"]
name = os.environ["NAME"]
body = os.environ.get("BODY", "")

try:
    data = json.loads(body)
    state = data.get("State", {})
    status = state.get("Status", "unknown")
    running = "running" if state.get("Running") else "stopped"
    image = data.get("Config", {}).get("Image", "-")
    print(f"{service:<16} {name:<28} {status:<12} {running:<8} {image}")
except Exception:
    print(f"{service:<16} {name:<28} missing      stopped  -")
PY
}

docker_socket_service_cmd() {
  docker_socket_available || return 1

  local action="${1:-}"
  shift || true

  case "$action" in
    stop)
      echo "[service] 当前环境使用 Docker socket 停止容器"
      for service in "$@"; do
        local name
        name="$(docker_container_name "$service")"
        echo "[service] 停止 $service：$name"
        docker_socket_request POST "/containers/$name/stop?t=30" || return 1
      done
      ;;
    up)
      if [[ "${1:-}" == "-d" ]]; then
        shift
      fi
      echo "[service] 当前环境使用 Docker socket 启动容器"
      for service in "$@"; do
        local name
        name="$(docker_container_name "$service")"
        echo "[service] 启动 $service：$name"
        docker_socket_request POST "/containers/$name/start" || return 1
      done
      ;;
    ps)
      echo "[service] 当前环境使用 Docker socket 查看容器状态"
      printf '%-16s %-28s %-12s %-8s %s\n' "SERVICE" "CONTAINER" "STATUS" "RUNNING" "IMAGE"
      for service in "$@"; do
        docker_socket_ps_one "$service"
      done
      ;;
    *)
      return 1
      ;;
  esac
}

print_affected_services() {
  echo "[service] 受影响服务列表："
  echo "  - web：Django ASGI / API 服务"
  echo "  - celery_worker：Celery Worker 后台任务"
  echo "  - celery_beat：Celery Beat 定时任务"
  echo "  - frontend：backoffice-web 前端 Nginx"
}

print_service_status() {
  local title="$1"
  echo ""
  echo "[service] $title"
  compose_cmd ps "${AFFECTED_SERVICES[@]}" || true
}

stop_affected_services() {
  echo ""
  echo "========================================"
  echo "[service] 开始停止受迁移影响的应用服务"
  echo "========================================"
  if resolve_service_base; then
    echo "[service] 服务目录：$SERVICE_BASE"
  elif docker_socket_available; then
    echo "[service] 未找到宿主机服务目录，改用 Docker socket 管理容器"
  else
    fail "[service] 未找到服务目录，也没有 Docker socket，无法停止受影响服务"
  fi
  print_affected_services
  print_service_status "停止前状态"
  echo "[service] 执行停止：docker compose stop ${AFFECTED_SERVICES[*]}"
  compose_cmd stop "${AFFECTED_SERVICES[@]}"
  print_service_status "停止后状态"
  SERVICES_STOPPED_BY_MIGRATION=1
}

start_affected_services() {
  if [[ "$SERVICES_STOPPED_BY_MIGRATION" != "1" || "$SERVICE_RESTORE_RUNNING" == "1" ]]; then
    return 0
  fi
  SERVICE_RESTORE_RUNNING=1

  echo ""
  echo "========================================"
  echo "[service] 迁移流程结束，开始启动之前关闭的相关服务"
  echo "========================================"
  if [[ -n "$SERVICE_BASE" ]]; then
    echo "[service] 服务目录：$SERVICE_BASE"
  else
    echo "[service] 使用 Docker socket 恢复容器"
  fi
  print_affected_services
  echo "[service] 执行启动：docker compose up -d ${AFFECTED_SERVICES[*]}"
  compose_cmd up -d "${AFFECTED_SERVICES[@]}"
  print_service_status "启动后状态"
}

prepare_affected_services() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[service] --dry-run 模式，不停止服务"
    return 0
  fi

  case "$SERVICE_CONTROL" in
    yes)
      echo "[service] 已指定 --stop-services，绕过询问，直接停止相关服务"
      stop_affected_services || true
      ;;
    no)
      echo "[service] --no-stop-services，跳过停止服务"
      ;;
    ask)
      echo ""
      echo "迁移会重置/写入 sparkservice 数据库，可能影响正在运行的 Django、Celery 等应用服务。"
      if [[ ! -t 0 ]]; then
        echo "[service] 非交互执行，绕过询问，直接停止相关服务"
        stop_affected_services || true
      elif ask_yes_no "是否先停止受影响的相关服务，并在迁移结束后自动启动"; then
        echo "[service] 用户选择停止相关服务"
        stop_affected_services || true
      else
        echo "[service] 用户选择不停服务，继续执行迁移"
      fi
      ;;
  esac
}

COMMANDS=(
  "00:zdk_migrate_00_check"
  "01:zdk_migrate_01_auth_users"
  "02:zdk_migrate_02_account_profiles"
  "03:zdk_migrate_03_social_identities"
  "04:zdk_migrate_04_trusted_devices"
  "05:zdk_migrate_05_account_audit"
  "06:zdk_migrate_06_members"
  "07:zdk_migrate_07_medical_cases"
  "08:zdk_migrate_08_clinical_children"
  "09:zdk_migrate_09_exam_reports"
  "10:zdk_migrate_10_health_exams"
  "11:zdk_migrate_11_prescriptions"
  "12:zdk_migrate_12_medication_plans"
  "13:zdk_migrate_13_medication_records"
  "14:zdk_migrate_14_files"
#  "15:zdk_migrate_15_ai_config"
  "16:zdk_migrate_16_chat"
  "17:zdk_migrate_17_app_version"
  "18:zdk_migrate_18_notifications"
  "98:zdk_migrate_98_repair_client_extra"
  "99:zdk_migrate_99_verify"
)

should_run_step() {
  local step="$1"
  if [[ "$step" -lt "$FROM_STEP" ]]; then
    return 1
  fi
  if [[ "$step" -gt "$TO_STEP" ]]; then
    return 1
  fi
  return 0
}

run_step() {
  local step="$1"
  local cmd="$2"
  local args=()

  if [[ "$DRY_RUN" -eq 1 ]]; then
    args+=(--dry-run)
  fi
  if [[ -n "$BATCH_SIZE" ]]; then
    args+=(--batch-size "$BATCH_SIZE")
  fi

  echo ""
  echo "========================================"
  if ((${#args[@]})); then
    echo "[$step] python manage.py $cmd ${args[*]}"
  else
    echo "[$step] python manage.py $cmd"
  fi
  echo "========================================"

  if ((${#args[@]})); then
    python manage.py "$cmd" "${args[@]}"
  else
    python manage.py "$cmd"
  fi
}

{
  echo "Migration started at $(date -Iseconds)"
  echo "BASE_DIR=$BASE_DIR"
  echo "NEW_DB=$DB_NAME@$DB_HOST:$DB_PORT"
  echo "OLD_DB=$ZDK_OLD_DB_NAME@$ZDK_OLD_DB_HOST:$ZDK_OLD_DB_PORT"
  echo "DRY_RUN=$DRY_RUN FROM=$FROM_STEP TO=$TO_STEP"
  echo "LOG_FILE=$LOG_FILE"
  echo "ERROR_LOG=$ERROR_LOG"
  echo ""

  trap 'start_affected_services || true' EXIT
  prepare_affected_services

  if [[ "$SKIP_RESET_DB" != "1" && "$DRY_RUN" != "1" && "$FROM_STEP" == "0" ]]; then
    echo "========================================"
    echo "[reset] ./scripts/migration/reset_db.sh -y"
    echo "========================================"
    "$BASE_DIR/scripts/migration/reset_db.sh" -y
    echo ""
  elif [[ "$SKIP_RESET_DB" == "1" ]]; then
    echo "[skip] SKIP_RESET_DB=1，跳过 scripts/migration/reset_db.sh"
  elif [[ "$DRY_RUN" == "1" ]]; then
    echo "[skip] --dry-run 模式，跳过 scripts/migration/reset_db.sh"
  elif [[ "$FROM_STEP" != "0" ]]; then
    echo "[skip] --from $FROM_STEP 续跑模式，跳过 scripts/migration/reset_db.sh"
  fi

  for entry in "${COMMANDS[@]}"; do
    step="${entry%%:*}"
    cmd="${entry#*:}"
    step_num=$((10#$step))

    if ! should_run_step "$step_num"; then
      echo "[skip] step $step ($cmd)"
      continue
    fi

    run_step "$step" "$cmd"
  done

  echo ""
  echo "Migration finished at $(date -Iseconds)"
} 2>&1 | tee "$LOG_FILE"
MIGRATION_EXIT=${PIPESTATUS[0]}

echo ""
echo "Full log: $LOG_FILE"

if [[ -s "$ERROR_LOG" ]]; then
  echo ""
  echo "========== Migration issue summary (deduplicated) =========="
  if command -v awk >/dev/null 2>&1; then
  awk '
    /\[SUMMARY\]/ && / count=/ {
      if ($0 ~ / fail: / || $0 ~ /fail:/) fail++
      else if ($0 ~ / skip: / || $0 ~ /skip:/) skip++
      else if ($0 ~ /stale /) warn++
      else if ($0 ~ /migrated=/) cmdsummary++
      print $0
    }
    END {
      printf "\nTotals: FAIL groups=%d SKIP groups=%d WARN groups=%d step summaries=%d\n", fail+0, skip+0, warn+0, cmdsummary+0
    }
  ' "$ERROR_LOG"
  fi
  echo "========== end summary =========="
  echo "Full detail: $ERROR_LOG"
fi

if [[ "$MIGRATION_EXIT" -ne 0 ]]; then
  echo ""
  echo "Migration FAILED (exit=$MIGRATION_EXIT). Fix errors above, then resume e.g.:"
  echo "  $0 --from 6"
  exit "$MIGRATION_EXIT"
fi

echo ""
echo "Migration completed successfully."
