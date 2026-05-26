#!/usr/bin/env bash
# 按顺序一键执行 ZhaodkDream -> SparkService 全部分批迁移命令。
#
# 用法:
#   ./scripts/migration/run_all_migration.sh              # 正式迁移
#   ./scripts/migration/run_all_migration.sh --dry-run    # 试跑（不写新库）
#   ./scripts/migration/run_all_migration.sh --from 06      # 从第 6 步起执行
#   ./scripts/migration/run_all_migration.sh --from 06 --to 10
#   SKIP_RESET_DB=1 ./scripts/migration/run_all_migration.sh  # 跳过 reset_db.sh
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

usage() {
  cat <<'EOF'
Usage: run_all_migration.sh [options]

Options:
  --dry-run           所有步骤加 --dry-run，不写新库
  --from N            从步骤 N 开始（0-18 或 99）
  --to N              到步骤 N 结束（默认 99）
  --batch-size N      传给各 migrate 命令的 --batch-size
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

if [[ "$SKIP_RESET_DB" != "1" && "$DRY_RUN" != "1" && "$FROM_STEP" == "0" ]]; then
  echo "========================================"
  echo "[reset] ./reset_db.sh -y"
  echo "========================================"
  "$BASE_DIR/reset_db.sh" -y
  echo ""
elif [[ "$SKIP_RESET_DB" == "1" ]]; then
  echo "[skip] SKIP_RESET_DB=1，跳过 reset_db.sh"
elif [[ "$DRY_RUN" == "1" ]]; then
  echo "[skip] --dry-run 模式，跳过 reset_db.sh"
elif [[ "$FROM_STEP" != "0" ]]; then
  echo "[skip] --from $FROM_STEP 续跑模式，跳过 reset_db.sh"
fi

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
