#!/usr/bin/env bash
set -euo pipefail
BASE="${SPARK_BASE:-/root/2026}"
RESET_REQUEST="${RESET_DATABASE_NAME:-}"
[[ "${RELEASE_TARGET_IP:-}" == "39.106.39.110" ]] || { echo 'Invalid release target' >&2; exit 2; }
PKG_PATH="${1:?Missing release package}"
[[ -f "$PKG_PATH" && -f "$BASE/.deploy.env" ]] || exit 2
set -a
source "$BASE/.deploy.env"
set +a
export RESET_DATABASE_NAME="$RESET_REQUEST" RELEASE_TARGET_IP=39.106.39.110
# Hold the lock in flock's parent process. --close prevents the long-lived
# containers started below from inheriting the lock descriptor through conmon.
if [[ "${DEPLOY_LOCK_GUARD:-}" != "$BASE/.deploy.lock" ]]; then
    export DEPLOY_LOCK_GUARD="$BASE/.deploy.lock"
    exec flock --nonblock --close "$BASE/.deploy.lock" "$0" "$PKG_PATH"
fi
TS="$(date +%Y%m%d_%H%M%S)"
TARGET="$BASE/releases/$TS"
mkdir -p "$TARGET" "$BASE/build" "$BASE/shared/logs" "$BASE/shared/media" "$BASE/shared/staticfiles" "$BASE/shared/frontend-dist"
tar -xzf "$PKG_PATH" -C "$TARGET"
[[ -s "$TARGET/manage.py" ]] || exit 2
# Keep a real snapshot directory for the Docker build context.
rm -rf "$BASE/build/current"
mkdir -p "$BASE/build/current"
tar -C "$TARGET" -cf - . | tar -C "$BASE/build/current" -xf -
cd "$BASE"
compose() { docker compose --env-file "$BASE/.deploy.env" -f "$BASE/docker-compose.yml" "$@"; }
compose build web
# Verify DB access before any destructive operation.
compose run --rm web python manage.py check --database default
if [[ -n "$RESET_REQUEST" ]]; then
    compose stop web celery_worker celery_beat
    compose run --rm -e RESET_DATABASE_NAME="$RESET_REQUEST" -e RELEASE_TARGET_IP=39.106.39.110 web python -c 'exec(open("/app/deployment/server/bin/reset_database.py").read())'
fi
compose run --rm web python manage.py makemigrations --check --dry-run
compose run --rm web python manage.py migrate --noinput
compose run --rm web python manage.py collectstatic --noinput
ln -sfn "$TARGET" "$BASE/current"
compose up -d --remove-orphans web celery_worker celery_beat frontend
for attempt in $(seq 1 30); do
    if curl -fsS -H 'X-Forwarded-Proto: https' "http://127.0.0.1:${DJANGO_PORT:-12026}/health/" >/dev/null; then
        compose ps
        echo "Release complete: $TARGET"
        exit 0
    fi
    sleep 2
done
echo 'Health check failed. Database reset cannot be rolled back automatically; services and release retained for diagnosis.' >&2
exit 1
