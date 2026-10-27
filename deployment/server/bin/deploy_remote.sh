#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BASE="${SPARK_BASE:-/root/2026}"
[[ "${RELEASE_TARGET_IP:-}" == 39.106.39.110 ]] || { echo 'Invalid release target' >&2; exit 2; }
[[ -z "${RESET_DATABASE_NAME:-}" ]] || { echo 'Database reset is not supported during a release' >&2; exit 2; }
PKG_PATH="${1:?Missing release package}"
STAGE="$(cd "$(dirname "$PKG_PATH")" && pwd)"
RELEASE_ID="$(basename "$STAGE")"
[[ "$RELEASE_ID" =~ ^[0-9]{8}_[0-9]{6}_[0-9]+_[0-9]+$ && "$STAGE" == "$BASE/uploads/$RELEASE_ID" ]] || exit 2
for tool in flock docker python3 sha256sum mysqldump gzip curl timeout; do
  command -v "$tool" >/dev/null || { echo "Missing remote tool: $tool" >&2; exit 2; }
done
exec 9>"$BASE/.deploy.lock"
flock -n 9 || { echo '已有部署持锁，本次未修改线上配置或服务。' >&2; exit 75; }

PHASE=verify-package
ACTIVATING=0
TEMPLATE_CHANGED=0
finish() {
  local result=$?
  trap - EXIT
  if [[ "$result" != 0 ]]; then
    if [[ "$TEMPLATE_CHANGED" == 1 && "$ACTIVATING" == 0 ]]; then
      for item in docker-compose.yml docker bin; do
        rm -rf "$BASE/$item"
        [[ ! -e "$STAGE/previous-template/$item" ]] || cp -a "$STAGE/previous-template/$item" "$BASE/$item"
      done
    fi
    printf 'Release failed: phase=%s, activating=%s, diagnostics=%s\n' "$PHASE" "$ACTIVATING" "$STAGE" >&2
    echo '迁移不会自动逆转；已进入切换阶段时请检查服务、配置备份与数据库备份后再处理。' >&2
  fi
  printf 'phase=%s\nexit_code=%s\nactivating=%s\n' "$PHASE" "$result" "$ACTIVATING" > "$STAGE/result.txt"
  exit "$result"
}
trap finish EXIT
(cd "$STAGE" && sha256sum -c sparkservice.tgz.sha256)
[[ "$(df -Pk "$BASE" | awk 'END {print $4}')" -ge 1048576 ]] || { echo '服务器可用空间不足 1 GiB。' >&2; exit 2; }
if [[ -d "$STAGE/frontend" ]]; then
  [[ -s "$STAGE/frontend/index.html" ]] || { echo 'Staged frontend is incomplete' >&2; exit 2; }
elif [[ ! -s "$BASE/shared/frontend-dist/index.html" ]]; then
  echo 'No staged or existing admin frontend' >&2; exit 2
fi
TARGET="$BASE/releases/$RELEASE_ID"
[[ ! -e "$TARGET" ]] || { echo 'Release directory already exists' >&2; exit 2; }
mkdir -p "$TARGET" "$BASE/build" "$BASE/shared/logs" "$BASE/shared/media" "$BASE/shared/staticfiles" "$BASE/shared/backups"
tar -xzf "$PKG_PATH" -C "$TARGET"
[[ -s "$TARGET/manage.py" ]] || exit 2
cp "$STAGE/release.txt" "$TARGET/RELEASE.txt"
if [[ ! -f "$STAGE/candidate.env" ]]; then
  [[ -s "$BASE/.deploy.env" ]] || { echo 'Missing production environment' >&2; exit 2; }
  cp "$BASE/.deploy.env" "$STAGE/candidate.env"
fi
chmod 600 "$STAGE/candidate.env"
export DEPLOY_ENV_PATH="$STAGE/candidate.env"
export SPARK_BACKEND_IMAGE="localhost/traveldiary-backend:$RELEASE_ID"

PHASE=prepare-template
mkdir -p "$STAGE/previous-template"
for item in docker-compose.yml docker bin; do
  [[ ! -e "$BASE/$item" ]] || cp -a "$BASE/$item" "$STAGE/previous-template/$item"
done
TEMPLATE_CHANGED=1
for item in docker-compose.yml docker bin; do
  [[ -e "$STAGE/server/$item" ]] || exit 2
  cp -a "$STAGE/server/$item" "$BASE/"
done
find "$BASE/bin" "$BASE/docker" -type f -name '*.sh' -exec chmod +x {} +
rm -rf "$BASE/build/current"
mkdir -p "$BASE/build/current"
tar -C "$TARGET" -cf - . | tar -C "$BASE/build/current" -xf -
cd "$BASE"
compose() { timeout "${COMPOSE_TIMEOUT:-900}" docker compose --env-file "$DEPLOY_ENV_PATH" -f "$BASE/docker-compose.yml" "$@" 9>&- < /dev/null; }
compose config > /dev/null
PHASE=build
compose build web
docker image inspect docker.m.daocloud.io/library/nginx:1.27-alpine 9>&- >/dev/null 2>&1 || compose pull frontend
# 在支付初始化、数据库备份/迁移和服务切换之前检查实际容器环境。
# 即使保留的是旧生产配置，也不能将开发环境身份或关闭的接收端继续发布。
PHASE=validate-environment
compose run --rm -T --no-deps web python deployment/server/bin/release_checks.py environment
PHASE=initialize-payment-key
mkdir -p "$BASE/shared/payment-secrets"
chmod 700 "$BASE/shared/payment-secrets"
compose run --rm -T --no-deps web python manage.py init_print_payment_key
PHASE=check-connections
compose run --rm -T --no-deps web python deployment/server/bin/release_checks.py connections
compose run --rm -T --no-deps web python manage.py check --database default
compose run --rm -T --no-deps web python manage.py makemigrations --check --dry-run

PHASE=backup-database
BACKUP="$BASE/shared/backups/pre_release_$RELEASE_ID.sql.gz"
mysqldump --single-transaction --routines --triggers sparkservice | gzip > "$BACKUP"
gzip -t "$BACKUP"
[[ -s "$BACKUP" ]] || exit 2
PHASE=migrate
compose run --rm -T --no-deps web python manage.py migrate --noinput
compose run --rm -T --no-deps web python manage.py collectstatic --noinput

PHASE=activate
ACTIVATING=1
[[ ! -f "$BASE/.deploy.env" ]] || cp -p "$BASE/.deploy.env" "$STAGE/previous.env"
python3 - "$STAGE/candidate.env" "$BASE/.deploy.env.next" "$SPARK_BACKEND_IMAGE" <<'PY'
from pathlib import Path
import sys
source, destination, image = sys.argv[1:]
lines = [line for line in Path(source).read_text().splitlines() if not line.lstrip().startswith(("SPARK_BACKEND_IMAGE=", "export SPARK_BACKEND_IMAGE="))]
Path(destination).write_text("\n".join(lines) + "\nSPARK_BACKEND_IMAGE=" + image + "\n")
PY
chmod 600 "$BASE/.deploy.env.next"
mv -f "$BASE/.deploy.env.next" "$BASE/.deploy.env"
export DEPLOY_ENV_PATH="$BASE/.deploy.env"
if [[ -d "$STAGE/frontend" ]]; then
  [[ ! -e "$BASE/shared/frontend-dist" ]] || mv "$BASE/shared/frontend-dist" "$STAGE/previous-frontend"
  find "$STAGE/frontend" -type d -exec chmod 755 {} +
  find "$STAGE/frontend" -type f -exec chmod 644 {} +
  mv "$STAGE/frontend" "$BASE/shared/frontend-dist"
fi
compose up -d --force-recreate --remove-orphans web celery_worker celery_beat frontend

PHASE=health
healthy() {
  local service container
  for service in web celery_worker celery_beat frontend; do
    container="$(docker ps -q --filter "label=com.docker.compose.project=$(basename "$BASE")" --filter "label=com.docker.compose.service=$service" 9>&-)" || return 1
    [[ -n "$container" ]] || return 1
    docker inspect "$container" 9>&- | python3 -c '
import json, sys
state = json.load(sys.stdin)[0]["State"]
health = state.get("Health", state.get("Healthcheck", {})).get("Status", "none")
sys.exit(0 if state["Running"] and health in ("healthy", "none") and (sys.argv[1] not in ("web", "frontend") or health == "healthy") else 1)
' "$service" || return 1
  done
  curl -fsS --connect-timeout 3 --max-time 5 -H 'X-Forwarded-Proto: https' http://127.0.0.1:12026/health/ >/dev/null || return 1
  curl -fsS --connect-timeout 3 --max-time 5 http://127.0.0.1:12018/health >/dev/null || return 1
  curl -fsS --connect-timeout 3 --max-time 5 http://127.0.0.1:12018/ >/dev/null || return 1
}
READY=0
for attempt in $(seq 1 60); do
  if healthy; then READY=1; break; fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo 'Four-service health check timed out' >&2; exit 1; }
PHASE=worker-check
COMPOSE_TIMEOUT=60 compose exec -T web python deployment/server/bin/release_checks.py workers
compose exec -T web python manage.py migrate --check
python3 - "$TARGET" "$BASE/current" <<'PY'
import os
import sys
target, current = sys.argv[1:]
temporary = current + ".next"
if os.path.lexists(temporary):
    os.unlink(temporary)
os.symlink(target, temporary)
os.replace(temporary, current)
PY
PHASE=complete
compose ps
echo "Release complete: $TARGET"
