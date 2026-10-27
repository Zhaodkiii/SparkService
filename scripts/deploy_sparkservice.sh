#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SRC_DIR="${SRC_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
SCRIPT_ROOT="$(cd "$(dirname "$0")" && pwd)"
REMOTE_HOST="${REMOTE_HOST:-root@39.106.39.110}"
source "$SCRIPT_ROOT/release_target_guard.sh"
validate_release_target "$SRC_DIR" "$REMOTE_HOST"
case "${1:-}" in
  --check-target) exit 0 ;;
  --preflight|"") MODE="${1:-release}" ;;
  *) echo "用法: $0 [--check-target|--preflight]" >&2; exit 2 ;;
esac

SERVER_TEMPLATE_DIR="${SERVER_TEMPLATE_DIR:-$SRC_DIR/deployment/server}"
FRONTEND_DIR="${FRONTEND_DIR:-$SRC_DIR/backoffice-web}"
REMOTE_BASE="${REMOTE_BASE:-/root/2026}"
# 保持历史行为：本地 .env 默认参与发布；候选副本按已校验生产目标转换同步身份。
DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-$SRC_DIR/.env}"
SYNC_DEPLOY_ENV="${SYNC_DEPLOY_ENV:-1}"
BUILD_FRONTEND_LOCAL="${BUILD_FRONTEND_LOCAL:-1}"
USE_RSYNC="${USE_RSYNC:-1}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
VITE_API_BASE_URL="${VITE_API_BASE_URL:-}"
PYTHON_BIN="${PYTHON_BIN:-$SRC_DIR/.venv/bin/python}"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN=python3
PHASE=local-preflight
LOCAL_STAGE=""
REMOTE_STAGE=""

cleanup() {
  local result=$?
  trap - EXIT
  [[ -z "$LOCAL_STAGE" ]] || rm -rf "$LOCAL_STAGE"
  if [[ "$result" != 0 ]]; then
    printf '发布失败：阶段=%s，退出码=%s。\n' "$PHASE" "$result" >&2
    [[ -z "$REMOTE_STAGE" ]] || printf '远端诊断目录：%s；请检查后再重试。\n' "$REMOTE_STAGE" >&2
  fi
  exit "$result"
}
trap cleanup EXIT

[[ "$REMOTE_BASE" =~ ^/[a-zA-Z0-9_/-]+$ && "$REMOTE_BASE" != / && "$REMOTE_BASE" != */../* && "$REMOTE_BASE" != */.. ]] || {
  echo 'REMOTE_BASE 必须是无空格、无 .. 的绝对目录，且不能为 /。' >&2; exit 2;
}
for flag in SYNC_DEPLOY_ENV BUILD_FRONTEND_LOCAL USE_RSYNC; do
  [[ "${!flag}" == 0 || "${!flag}" == 1 ]] || { echo "$flag 只能为 0 或 1。" >&2; exit 2; }
done
[[ "${CANCEL_RUNNING_DEPLOY:-0}" == 0 ]] || {
  echo '不再自动终止旧部署；请先诊断持锁任务，完成处理后重新发布。' >&2; exit 2;
}
[[ -z "${RESET_DATABASE_NAME:-}" ]] || {
  echo '普通发布不允许清空数据库；请使用单独审查的数据库维护流程。' >&2; exit 2;
}
for tool in ssh scp tar shasum "$PYTHON_BIN"; do
  command -v "$tool" >/dev/null || { echo "缺少命令：$tool" >&2; exit 2; }
done
if [[ "$USE_RSYNC" == 1 || "$BUILD_FRONTEND_LOCAL" == 1 ]]; then
  command -v rsync >/dev/null || { echo '缺少 rsync。' >&2; exit 2; }
fi
for file in docker-compose.yml docker/backend.Dockerfile docker/scripts/backend-entrypoint.sh docker/nginx/backoffice.conf bin/deploy_remote.sh bin/release_checks.py bin/prepare_production_env.py; do
  [[ -s "$SERVER_TEMPLATE_DIR/$file" ]] || { echo "缺少服务器模板：$file" >&2; exit 2; }
done
bash -n "$SERVER_TEMPLATE_DIR/bin/deploy_remote.sh"
bash -n "$SERVER_TEMPLATE_DIR/docker/scripts/backend-entrypoint.sh"
LOCAL_STAGE="$(mktemp -d "${TMPDIR:-/tmp}/sparkservice-release.XXXXXX")"
if [[ "$SYNC_DEPLOY_ENV" == 1 ]]; then
  [[ -s "$DEPLOY_ENV_FILE" ]] || { echo '发布配置文件不存在或为空。' >&2; exit 2; }
  cp "$DEPLOY_ENV_FILE" "$LOCAL_STAGE/candidate.env"
  chmod 600 "$LOCAL_STAGE/candidate.env"
  "$PYTHON_BIN" "$SERVER_TEMPLATE_DIR/bin/prepare_production_env.py" "$LOCAL_STAGE/candidate.env"
  "$PYTHON_BIN" "$SERVER_TEMPLATE_DIR/bin/release_checks.py" config "$LOCAL_STAGE/candidate.env"
else
  echo '配置策略：保留服务器 .deploy.env；本地 .env 不参与发布。'
fi
if [[ "$BUILD_FRONTEND_LOCAL" == 1 ]]; then
  command -v pnpm >/dev/null || { echo '缺少 pnpm。' >&2; exit 2; }
  [[ -s "$FRONTEND_DIR/package.json" && -s "$FRONTEND_DIR/pnpm-lock.yaml" ]] || exit 2
fi
[[ "$MODE" != --preflight ]] || { echo '本地预检通过，未连接服务器。'; exit 0; }

PHASE=frontend-build
if [[ "$BUILD_FRONTEND_LOCAL" == 1 ]]; then
  (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile && VITE_API_BASE_URL="$VITE_API_BASE_URL" pnpm build)
  [[ -s "$FRONTEND_DIR/dist/index.html" ]] || { echo '后台构建未生成 index.html。' >&2; exit 2; }
fi

PHASE=package
RELEASE_ID="$(date +%Y%m%d_%H%M%S)_$$_${RANDOM}"
PKG_NAME=sparkservice.tgz
EXCLUDES=(
  --exclude .secrets --exclude .git --exclude .env --exclude '.env.*' --exclude .deploy.env --exclude '.deploy.env.*'
  --exclude 数据库备份 --exclude apns_keys --exclude '*.sql' --exclude '*.sql.gz'
  --exclude '*.sqlite3' --exclude '*.rdb' --exclude tmp --exclude scripts/后台管理/logs
  --exclude .idea --exclude .vscode --exclude .venv --exclude venv --exclude __pycache__
  --exclude '*.pyc' --exclude .DS_Store --exclude node_modules --exclude backoffice-web/dist
  --exclude share-web --exclude logs --exclude run --exclude media --exclude staticfiles
  --exclude .pytest_cache --exclude .vite --exclude scripts/deploy_sparkservice.sh
)
COPYFILE_DISABLE=1 tar -czf "$LOCAL_STAGE/$PKG_NAME" "${EXCLUDES[@]}" -C "$SRC_DIR" .
(cd "$LOCAL_STAGE" && shasum -a 256 "$PKG_NAME" > "$PKG_NAME.sha256")
printf 'release=%s\nbranch=%s\ncommit=%s\ndirty=%s\n' "$RELEASE_ID" \
  "$(git -C "$SRC_DIR" branch --show-current)" "$(git -C "$SRC_DIR" rev-parse HEAD)" \
  "$(if [[ -n "$(git -C "$SRC_DIR" status --porcelain)" ]]; then echo yes; else echo no; fi)" > "$LOCAL_STAGE/release.txt"

PHASE=upload
SSH_OPTIONS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
REMOTE_STAGE="$REMOTE_BASE/uploads/$RELEASE_ID"
ssh "${SSH_OPTIONS[@]}" "$REMOTE_HOST" "umask 077; mkdir -p '$REMOTE_STAGE/server'"
scp "${SSH_OPTIONS[@]}" "$LOCAL_STAGE/$PKG_NAME" "$LOCAL_STAGE/$PKG_NAME.sha256" "$LOCAL_STAGE/release.txt" "$REMOTE_HOST:$REMOTE_STAGE/"
if [[ "$USE_RSYNC" == 1 ]]; then
  rsync -az -e "ssh ${SSH_OPTIONS[*]}" --exclude .deploy.env --exclude '.deploy.env.*' --exclude shared --exclude uploads --exclude releases \
    "$SERVER_TEMPLATE_DIR/" "$REMOTE_HOST:$REMOTE_STAGE/server/"
else
  COPYFILE_DISABLE=1 tar -czf "$LOCAL_STAGE/server.tgz" --exclude .deploy.env --exclude '.deploy.env.*' --exclude shared --exclude uploads --exclude releases -C "$SERVER_TEMPLATE_DIR" .
  scp "${SSH_OPTIONS[@]}" "$LOCAL_STAGE/server.tgz" "$REMOTE_HOST:$REMOTE_STAGE/"
  ssh "${SSH_OPTIONS[@]}" "$REMOTE_HOST" "tar -xzf '$REMOTE_STAGE/server.tgz' -C '$REMOTE_STAGE/server'"
fi
if [[ "$SYNC_DEPLOY_ENV" == 1 ]]; then
  scp "${SSH_OPTIONS[@]}" "$LOCAL_STAGE/candidate.env" "$REMOTE_HOST:$REMOTE_STAGE/candidate.env"
fi
if [[ "$BUILD_FRONTEND_LOCAL" == 1 ]]; then
  rsync -az -e "ssh ${SSH_OPTIONS[*]}" "$FRONTEND_DIR/dist/" "$REMOTE_HOST:$REMOTE_STAGE/frontend/"
fi

PHASE=remote-release
printf -v REMOTE_COMMAND 'SPARK_BASE=%q RELEASE_TARGET_IP=39.106.39.110 PIP_INDEX_URL=%q bash %q %q' \
  "$REMOTE_BASE" "$PIP_INDEX_URL" "$REMOTE_STAGE/server/bin/deploy_remote.sh" "$REMOTE_STAGE/$PKG_NAME"
ssh "${SSH_OPTIONS[@]}" "$REMOTE_HOST" "$REMOTE_COMMAND" < /dev/null
echo "SparkService deployed: $RELEASE_ID"
