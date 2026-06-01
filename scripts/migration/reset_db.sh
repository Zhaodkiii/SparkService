#!/usr/bin/env bash
# ==============================================================================
# 脚本名称: reset_django_env.sh
# 描述: 用于 Django 开发环境的快速重置。
#       1. 执行数据库重置工具 (reset_db.sh) 的不同模式（预览/交互/自动）。
#       2. 自动化配置环境变量，确保脚本在项目根目录下安全运行。
# ==============================================================================

# --- 1. 数据库重置操作示例 ---
# 注意：以下为调用说明，根据需求取消注释或在命令行调用
# cd /Users/hua/Downloads/Reference/SparkService
# ./scripts/migration/reset_db.sh --dry-run  # 预览（安全检查，不执行实际删除）
# ./scripts/migration/reset_db.sh            # 正式执行（带确认提示）
# ./scripts/migration/reset_db.sh -y         # 跳过确认（强制执行）

# --- 2. 环境初始化与安全设置 ---
# set -e: 遇到错误立即停止执行
# set -u: 遇到未定义变量报错
# set -o pipefail: 管道命令中只要有一个失败则整体返回失败
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="$BASE_DIR/.venv"

DRY_RUN=0      # 预览模式：只展示将要执行的操作，不实际删除
ASSUME_YES=0   # 跳过确认提示

# ---------- 新库 sparkservice（与 run_all_migration.sh 保持一致，写死本机配置） ----------
DB_ENGINE="django.db.backends.mysql"
DB_HOST="127.0.0.1"
DB_PORT="3306"
DB_NAME="sparkservice"
DB_USER="root"
DB_PASSWORD="Zhao1029*"
DB_CONN_MAX_AGE="60"

usage() {
  cat <<'EOF'
用法: ./scripts/migration/reset_db.sh [选项]

重置迁移历史并重建数据库（仅限开发环境）。

选项:
  -y, --yes       跳过确认提示
  -n, --dry-run   预览将要删除/执行的操作，不实际改动
  -h, --help      显示此帮助

脚本执行步骤:
  1. 删除各 app 下 */migrations/ 中的迁移文件（保留 __init__.py）
  2. 连接 MySQL，DROP + CREATE 重建 sparkservice 库
  3. 运行 manage.py makemigrations + migrate

以下目录在迁移清理时会被跳过（绝不触碰）:
  .venv/  .git/  node_modules/  backoffice-web/  .pytest_cache/  .idea/
EOF
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes) ASSUME_YES=1; shift ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知选项: $1" >&2; usage >&2; exit 1 ;;
  esac
done

# 激活虚拟环境（若存在）
if [[ -f "$VENV_DIR/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
fi

cd "$BASE_DIR"

# 校验是否在 Django 项目根目录
if [[ ! -f "$BASE_DIR/manage.py" ]]; then
  echo "错误: 未找到 manage.py，请在 SparkService 项目根目录运行此脚本。" >&2
  exit 1
fi

# 导出数据库配置，供 manage.py makemigrations / migrate 使用
export DB_ENGINE DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD DB_CONN_MAX_AGE

# 连接 MySQL，删除 sparkservice 库并重建（在 makemigrations / migrate 之前执行）
reset_database() {
  echo "数据库连接信息:"
  echo "  引擎: ${DB_ENGINE}"
  echo "  主机: ${DB_HOST}:${DB_PORT}"
  echo "  用户: ${DB_USER}"
  echo "  库名: ${DB_NAME}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  操作: DROP DATABASE IF EXISTS \`${DB_NAME}\`; CREATE DATABASE \`${DB_NAME}\` CHARACTER SET utf8mb4;"
    return 0
  fi

  echo "正在连接 MySQL ${DB_HOST}:${DB_PORT} ..."
  echo "正在删除数据库 \`${DB_NAME}\` ..."
  echo "正在重建数据库 \`${DB_NAME}\` ..."

  if command -v mysql >/dev/null 2>&1; then
    MYSQL_PWD="$DB_PASSWORD" mysql \
      -h"$DB_HOST" \
      -P"$DB_PORT" \
      -u"$DB_USER" \
      --default-character-set=utf8mb4 \
      -e "DROP DATABASE IF EXISTS \`${DB_NAME}\`; CREATE DATABASE \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
  else
    echo "未找到 mysql 命令，改用 Python PyMySQL 重建数据库..."
    python3 - <<'PY'
import os
import pymysql

db_name = os.environ["DB_NAME"]
connection = pymysql.connect(
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    charset="utf8mb4",
    autocommit=True,
)
try:
    with connection.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        cursor.execute(
            f"CREATE DATABASE `{db_name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
finally:
    connection.close()
PY
  fi

  echo "已重建 MySQL 数据库: ${DB_NAME}"
}

# find 的 prune 表达式：跳过依赖目录和 IDE 目录（绝不扫描 .venv 内的 migrations）
FIND_PRUNE=(
  \( \
    -path "$BASE_DIR/.venv" -o -path "$BASE_DIR/.venv/*" \
    -o -path "$BASE_DIR/.git" -o -path "$BASE_DIR/.git/*" \
    -o -path "$BASE_DIR/node_modules" -o -path "$BASE_DIR/node_modules/*" \
    -o -path "$BASE_DIR/backoffice-web" -o -path "$BASE_DIR/backoffice-web/*" \
    -o -path "$BASE_DIR/.pytest_cache" -o -path "$BASE_DIR/.pytest_cache/*" \
    -o -path "$BASE_DIR/.idea" -o -path "$BASE_DIR/.idea/*" \
  \) -prune -o
)

# 列出待删除的迁移文件
# 匹配规则：[0-9]*.py 仅匹配编号迁移（如 0001_initial.py），不会误删 __init__.py
list_migration_files_to_delete() {
  find "$BASE_DIR" "${FIND_PRUNE[@]}" \
    -type f -path "*/migrations/[0-9]*.py" -print

  # 清理 migrations 目录下的编译缓存
  find "$BASE_DIR" "${FIND_PRUNE[@]}" \
    -type f \( -path "*/migrations/*.pyc" -o -path "*/migrations/__pycache__/*" \) -print
}

# 统计行数（用于计算待删除文件数量）
count_lines() {
  local n=0
  local line
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    n=$((n + 1))
  done
  echo "$n"
}

MIGRATION_FILES="$(list_migration_files_to_delete || true)"
MIGRATION_COUNT="$(printf '%s\n' "$MIGRATION_FILES" | count_lines)"

echo "SparkService 数据库重置（仅限开发环境）"
echo "项目根目录: $BASE_DIR"
echo "待删除迁移文件数: $MIGRATION_COUNT"
if [[ "$MIGRATION_COUNT" -gt 0 ]]; then
  printf '%s\n' "$MIGRATION_FILES"
fi

# 预览模式：展示数据库重置计划后退出
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  echo "[预览] 数据库重置计划:"
  reset_database
  echo
  echo "[预览] 将执行: python manage.py makemigrations && python manage.py migrate"
  exit 0
fi

# 执行前确认（-y 可跳过）
if [[ "$ASSUME_YES" -ne 1 ]]; then
  echo
  read -r -p "此操作将删除所有本地迁移文件并重置数据库，是否继续？ [y/N] " reply
  case "$reply" in
    y|Y|yes|YES) ;;
    *) echo "已取消。"; exit 1 ;;
  esac
fi

echo
echo "正在删除迁移文件..."
if [[ "$MIGRATION_COUNT" -gt 0 ]]; then
  while IFS= read -r file; do
    [[ -n "$file" ]] || continue
    rm -f "$file"
  done <<< "$MIGRATION_FILES"
fi

# 清理 migrations 下空的 __pycache__ 目录
find "$BASE_DIR" "${FIND_PRUNE[@]}" \
  -type d -path "*/migrations/__pycache__" -empty -print -delete 2>/dev/null || true

echo
echo "正在连接数据库并重建空库（makemigrations / migrate 之前）..."
reset_database

echo "正在重新生成迁移..."
python3 manage.py makemigrations

echo "正在应用迁移..."
python3 manage.py migrate

echo
echo "完成。迁移历史已清零，数据库已重建。"
