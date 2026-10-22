#!/usr/bin/env bash
set -euo pipefail
umask 077

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TOOL_DIR="${PRESET_TOOL_DIR:-/Users/dream/Documents/project/TravelDiary/PSD转换工具}"
LOCAL_ENV="${PRESET_LOCAL_ENV:-$TOOL_DIR/.env.publish}"
PYTHON="${PRESET_PYTHON:-$SRC_DIR/.venv/bin/python}"
REMOTE_HOST="${REMOTE_HOST:-root@39.106.39.110}"
REMOTE_BASE="${REMOTE_BASE:-/root/2026}"
MODE=apply
case "${1:-}" in
  --dry-run) MODE=check ;;
  --check-target) MODE=target ;;
  --help|-h)
    echo '用法：bash scripts/sync_local_catalog.sh [--dry-run|--check-target]'
    echo '默认执行：本机公开预设及素材库、A5/B5 印刷配置覆盖服务器；先备份，保留私人定制和订单。'
    exit 0 ;;
  '') ;;
  *) echo '未知参数；使用 --help 查看说明。' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo '参数过多' >&2; exit 2; }
source "$SRC_DIR/scripts/release_target_guard.sh"
validate_release_target "$SRC_DIR" "$REMOTE_HOST"
git -C "$SRC_DIR" rev-parse HEAD
[[ "$(git -C "$SRC_DIR" branch --show-current)" == TravelDiary ]] || { echo '同步仅支持 TravelDiary 分支' >&2; exit 2; }
[[ "$MODE" != target ]] || exit 0
[[ "$REMOTE_BASE" =~ ^/[a-zA-Z0-9/_-]+$ ]] || { echo '非法远端部署路径' >&2; exit 2; }
[[ -x "$PYTHON" && -f "$LOCAL_ENV" ]] || { echo '后端 Python 或本机发布配置不存在' >&2; exit 2; }
for tool in ssh scp; do command -v "$tool" >/dev/null; done
mkdir -p "$SRC_DIR/tmp/preset-sync"
RUN_DIR="$(mktemp -d "$SRC_DIR/tmp/preset-sync/$(TZ=Asia/Shanghai date +%Y%m%d_%H%M%S)_XXXXXX")"
echo "本次本地记录：$RUN_DIR"
"$PYTHON" "$SRC_DIR/scripts/preset_catalog_transfer.py" export "$RUN_DIR/catalog.json" \
  --env-file "$LOCAL_ENV" --report "$RUN_DIR/export-report.json"
cp "$SRC_DIR/scripts/preset_catalog_transfer.py" "$RUN_DIR/preset_catalog_transfer.py"

cat > "$RUN_DIR/remote.sh" <<'REMOTE'
#!/usr/bin/env bash
set -euo pipefail
umask 077
base="$1"
run="$2"
mode="$3"
cd "$base"
compose() { docker compose --env-file "$base/.deploy.env" -f "$base/docker-compose.yml" "$@"; }
transfer() {
  compose run --rm -T --entrypoint python -e RELEASE_TARGET_IP=39.106.39.110 \
    -v "$run:/catalog-transfer:rw" web /catalog-transfer/preset_catalog_transfer.py \
    "$@" < /dev/null
}
for service in web celery_worker celery_beat frontend; do
  container="$(docker ps -q --filter label=com.docker.compose.project=2026 --filter label=com.docker.compose.service="$service")"
  [[ -n "$container" ]] || { echo "服务未运行：$service" >&2; exit 1; }
done
transfer check /catalog-transfer/catalog.json --report /catalog-transfer/check-report.json
if [[ "$mode" == check ]]; then
  echo '只读预检通过；未停止服务、未修改数据库。'
  exit 0
fi
command -v mariadb-dump >/dev/null
mariadb-dump --single-transaction --routines --triggers sparkservice | gzip > "$run/database.sql.gz"
gzip -t "$run/database.sql.gz"
stat -c '数据库备份：%n（%s 字节）' "$run/database.sql.gz"
restart_needed=1
finish() {
  result=$?
  trap - EXIT
  if [[ "$restart_needed" == 1 ]]; then
    if ! compose start web celery_worker celery_beat < /dev/null; then
      echo '恢复服务失败，请检查容器；数据库备份保留。' >&2
      exit 1
    fi
  fi
  exit "$result"
}
trap finish EXIT
trap 'exit 130' INT TERM HUP
compose stop web celery_worker celery_beat < /dev/null
transfer apply /catalog-transfer/catalog.json --verified-report /catalog-transfer/check-report.json \
  --report /catalog-transfer/import-report.json
compose start web celery_worker celery_beat < /dev/null
restart_needed=0
for attempt in $(seq 1 30); do
  if curl -fsS -H 'X-Forwarded-Proto: https' http://127.0.0.1:12026/health/ >/dev/null; then
    curl -fsS https://diary.dreamwhale.top/health/ >/dev/null
    curl -fsS https://diary.dreamwhale.top/ >/dev/null
    for service in web celery_worker celery_beat frontend; do
      container="$(docker ps -q --filter label=com.docker.compose.project=2026 --filter label=com.docker.compose.service="$service")"
      [[ -n "$container" ]] || { echo "导入已提交，但服务未恢复：$service" >&2; exit 1; }
    done
    web="$(docker ps -q --filter label=com.docker.compose.project=2026 --filter label=com.docker.compose.service=web)"
    docker exec "$web" python -c 'from SparkService.celery import app; assert app.control.inspect(timeout=5).ping(), "Celery worker 未响应"; print("Celery worker ping 通过")' < /dev/null
    echo "目录及印刷配置同步完成，逐行核对通过。备份和报告：$run"
    exit 0
  fi
  sleep 2
done
echo '导入已提交，但 API 健康检查失败；保留备份，请查看服务日志。' >&2
exit 1
REMOTE

REMOTE_RUN="$REMOTE_BASE/shared/backups/preset-sync/$(basename "$RUN_DIR")"
ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" "umask 077; mkdir -p '$REMOTE_RUN'"
scp -q "$RUN_DIR/catalog.json" "$RUN_DIR/preset_catalog_transfer.py" "$RUN_DIR/remote.sh" "$REMOTE_HOST:$REMOTE_RUN/"
echo '正在预检服务器关联和全部 OSS 依赖；每 500 个对象输出进度。'
set +e
ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" \
  "flock --nonblock --close '$REMOTE_BASE/.deploy.lock' bash '$REMOTE_RUN/remote.sh' '$REMOTE_BASE' '$REMOTE_RUN' '$MODE'" \
  2>&1 | tee "$RUN_DIR/remote.log"
result=${PIPESTATUS[0]}
set -e
for report in check-report.json import-report.json; do
  scp -q "$REMOTE_HOST:$REMOTE_RUN/$report" "$RUN_DIR/$report" 2>/dev/null || true
done
echo "远端备份和报告：$REMOTE_RUN"
echo "本地完整日志：$RUN_DIR/remote.log"
if [[ "$result" != 0 ]]; then
  tail -n 25 "$RUN_DIR/remote.log"
  echo '同步失败；不会自动重复导入。请依据日志确认事务是否已提交。' >&2
fi
exit "$result"
