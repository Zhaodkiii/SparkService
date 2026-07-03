#!/usr/bin/env bash
# 启用严格模式：遇到错误立即退出、使用未定义变量退出、管道失败时整体失败
set -euo pipefail

# ========== 1. 定义基础路径与配置变量 ==========
# 项目源码目录（默认取当前脚本的上一级目录）
SRC_DIR="${SRC_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
# 服务器模板目录（存放部署脚本等）
SERVER_TEMPLATE_DIR="${SERVER_TEMPLATE_DIR:-$(cd "$SRC_DIR/.." && pwd)/2026}"
# 前端后台目录
FRONTEND_DIR="${FRONTEND_DIR:-$SRC_DIR/backoffice-web}"
# 医疗分享前端目录
SHARE_WEB_DIR="${SHARE_WEB_DIR:-$SRC_DIR/share-web}"
# 远程服务器地址（用户名@IP）
REMOTE_HOST="${REMOTE_HOST:-root@39.106.39.110}"
# 远程服务器部署根目录
REMOTE_BASE="${REMOTE_BASE:-/root/2026}"
# 医疗分享前端静态目录（由服务器系统 Nginx 托管）
SHARE_WEB_REMOTE_DIR="${SHARE_WEB_REMOTE_DIR:-/var/www/share.dreamwhale.top}"
# 远程上传文件存放目录
UPLOAD_DIR="$REMOTE_BASE/uploads"
# 远程脚本存放目录
REMOTE_BIN="$REMOTE_BASE/bin"
# 远程执行的部署脚本路径
REMOTE_DEPLOY="$REMOTE_BIN/deploy_remote.sh"
# PyPI 镜像源（阿里云 HTTPS，避免新版 pip 拒绝不可信 HTTP 源）
PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
# 前端生产 API 地址
VITE_API_BASE_URL="${VITE_API_BASE_URL:-https://api.dreamwhale.top}"
# 分享前端 API 地址；默认留空，使用同域 /api/ 反代到后端
SHARE_WEB_API_BASE_URL="${SHARE_WEB_API_BASE_URL:-}"
# 是否在本地构建前端并上传 dist，避免 2C2G 服务器构建时卡死
BUILD_FRONTEND_LOCAL="${BUILD_FRONTEND_LOCAL:-1}"
# 是否在本地构建医疗分享前端并上传 dist
BUILD_SHARE_WEB_LOCAL="${BUILD_SHARE_WEB_LOCAL:-1}"
# 是否使用 rsync 同步（1=启用，0=关闭）
USE_RSYNC="${USE_RSYNC:-1}"
# 是否在新部署前取消服务器上未完成的旧部署（1=启用）
CANCEL_RUNNING_DEPLOY="${CANCEL_RUNNING_DEPLOY:-1}"

# ========== 2. 生成打包信息 ==========
# 时间戳：用于区分版本
TS="$(date +%Y%m%d_%H%M%S)"
# 打包文件名
PKG_NAME="sparkservice_${TS}.tgz"
# 本地临时打包路径
PKG_PATH="/tmp/$PKG_NAME"

# ========== 3. 打包排除文件/目录列表 ==========
# 这些文件不会被上传到服务器（版本控制、环境、缓存、日志、编译文件等）
EXCLUDES=(
  --exclude ".git"
  --exclude ".env"
  --exclude ".idea"
  --exclude ".vscode"
  --exclude ".venv"
  --exclude "venv"
  --exclude "**/__pycache__"
  --exclude "**/*.pyc"
  --exclude ".DS_Store"
  --exclude "**/.DS_Store"
  --exclude "node_modules"
  --exclude "backoffice-web/node_modules"
  --exclude "backoffice-web/dist"
  --exclude "share-web/node_modules"
  --exclude "share-web/dist"
  --exclude "logs"
  --exclude "run"
  --exclude "media"
  --exclude "staticfiles"
  --exclude "db.sqlite3"
  --exclude "dump.rdb"
  --exclude ".pytest_cache"
  --exclude "scripts/deploy_sparkservice.sh"
)

# ========== 4. 环境检查 ==========
# 检查 ssh 命令是否存在
command -v ssh >/dev/null || { echo "ssh not found" >&2; exit 2; }
# 检查 scp 命令是否存在
command -v scp >/dev/null || { echo "scp not found" >&2; exit 2; }
# 检查源码目录是否存在
[[ -d "$SRC_DIR" ]] || { echo "SRC_DIR not found: $SRC_DIR" >&2; exit 2; }
# 检查服务器模板脚本目录是否存在
[[ -d "$SERVER_TEMPLATE_DIR/bin" ]] || { echo "server template bin not found: $SERVER_TEMPLATE_DIR/bin" >&2; exit 2; }
if [[ "$BUILD_FRONTEND_LOCAL" == "1" ]]; then
  [[ -d "$FRONTEND_DIR" ]] || { echo "FRONTEND_DIR not found: $FRONTEND_DIR" >&2; exit 2; }
  command -v pnpm >/dev/null || { echo "pnpm not found" >&2; exit 2; }
fi
if [[ "$BUILD_SHARE_WEB_LOCAL" == "1" ]]; then
  [[ -d "$SHARE_WEB_DIR" ]] || { echo "SHARE_WEB_DIR not found: $SHARE_WEB_DIR" >&2; exit 2; }
  command -v npm >/dev/null || { echo "npm not found" >&2; exit 2; }
fi

# ========== 5. 远程初始化 ==========
# 如果上一次部署卡在 docker build / pull / migrate，会持有 /root/2026/.deploy.lock。
# 新部署前先终止旧 deploy_remote.sh，让 flock 自动释放，避免一直提示“已有部署任务正在执行”。
if [[ "$CANCEL_RUNNING_DEPLOY" == "1" ]]; then
  echo "==> 检查并取消服务器上未完成的旧部署任务"
  ssh "$REMOTE_HOST" 'REMOTE_DEPLOY="'"$REMOTE_DEPLOY"'"; python3 - "$REMOTE_DEPLOY" <<'"'"'PY'"'"'
import os
import signal
import subprocess
import sys
import time

remote_deploy = sys.argv[1]
current_pid = os.getpid()

def find_deploy_pids():
    output = subprocess.check_output(["ps", "-eo", "pid=,args="], universal_newlines=True)
    pids = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_text, _, args = line.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == current_pid:
            continue
        if remote_deploy in args and "deploy_remote.sh" in args and "python3.12 -" not in args:
            pids.append(pid)
    return pids

pids = find_deploy_pids()
if not pids:
    print("没有发现旧部署任务")
    raise SystemExit(0)

print("发现旧部署任务，正在终止: " + " ".join(map(str, pids)))
for pid in pids:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

time.sleep(3)
pids = find_deploy_pids()
if pids:
    print("旧部署任务未退出，强制终止: " + " ".join(map(str, pids)))
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
PY
  ' || {
    echo "⚠️  取消旧部署任务时 SSH 返回异常，继续执行新的部署"
  }
  ssh "$REMOTE_HOST" 'REMOTE_DEPLOY="'"$REMOTE_DEPLOY"'"; python3 - "$REMOTE_DEPLOY" <<'"'"'PY'"'"'
import os
import subprocess
import sys

remote_deploy = sys.argv[1]
current_pid = os.getpid()
output = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
for line in output.splitlines():
    line = line.strip()
    if not line:
        continue
    pid_text, _, args = line.partition(" ")
    try:
        pid = int(pid_text)
    except ValueError:
        continue
    if pid != current_pid and remote_deploy in args and "deploy_remote.sh" in args and "python3.12 -" not in args:
        print("⚠️  仍检测到旧部署任务残留，但继续尝试新部署")
        raise SystemExit(0)
print("旧部署任务已清理，继续部署")
PY
  ' || true
fi

# 在远程服务器创建必要目录
ssh "$REMOTE_HOST" "mkdir -p '$UPLOAD_DIR' '$REMOTE_BIN' '$REMOTE_BASE/shared/logs' '$REMOTE_BASE/shared/media' '$REMOTE_BASE/shared/staticfiles' '$REMOTE_BASE/shared/backups'"
# 同步 Docker Compose 服务器模板，但不覆盖生产 .deploy.env，也不上传运行数据。
if command -v rsync >/dev/null 2>&1; then
  rsync -az \
    --exclude ".deploy.env" \
    --exclude "releases" \
    --exclude "uploads" \
    --exclude "shared" \
    "$SERVER_TEMPLATE_DIR"/ "$REMOTE_HOST:$REMOTE_BASE/"
else
  scp "$SERVER_TEMPLATE_DIR"/docker-compose.yml "$REMOTE_HOST:$REMOTE_BASE/"
  scp "$SERVER_TEMPLATE_DIR"/.docker.env.example "$REMOTE_HOST:$REMOTE_BASE/"
  scp "$SERVER_TEMPLATE_DIR"/.deploy.env.example "$REMOTE_HOST:$REMOTE_BASE/"
  scp -r "$SERVER_TEMPLATE_DIR"/bin "$SERVER_TEMPLATE_DIR"/docker "$REMOTE_HOST:$REMOTE_BASE/"
fi
# 给远程脚本添加执行权限
ssh "$REMOTE_HOST" "chmod +x '$REMOTE_BIN'/*.sh '$REMOTE_BASE'/docker/scripts/*.sh '$REMOTE_BASE'/docker/backup/*.sh"

# ========== 6. 本地构建前端并上传 ==========
# 2C2G 服务器不适合跑 vue-tsc/vite build；前端在本机产出 dist，服务器只用 nginx 托管静态文件。
if [[ "$BUILD_FRONTEND_LOCAL" == "1" ]]; then
  echo "==> 本地构建前端：VITE_API_BASE_URL=$VITE_API_BASE_URL"
  (cd "$FRONTEND_DIR" && VITE_API_BASE_URL="$VITE_API_BASE_URL" pnpm install --frozen-lockfile && VITE_API_BASE_URL="$VITE_API_BASE_URL" pnpm build)
  ssh "$REMOTE_HOST" "mkdir -p '$REMOTE_BASE/shared/frontend-dist'"
  rsync -az --delete "$FRONTEND_DIR/dist"/ "$REMOTE_HOST:$REMOTE_BASE/shared/frontend-dist/"
fi

# ========== 6.1 本地构建医疗分享前端并上传 ==========
# share-web 由服务器系统 Nginx 托管，不属于 Docker Compose；这里直接同步到 /var/www/share.dreamwhale.top。
if [[ "$BUILD_SHARE_WEB_LOCAL" == "1" ]]; then
  echo "==> 本地构建医疗分享前端：SHARE_WEB_API_BASE_URL=${SHARE_WEB_API_BASE_URL:-同域 /api/}"
  (cd "$SHARE_WEB_DIR" && npm ci && VITE_API_BASE_URL="$SHARE_WEB_API_BASE_URL" npm run build)
  ssh "$REMOTE_HOST" "mkdir -p '$SHARE_WEB_REMOTE_DIR'"
  rsync -az --delete "$SHARE_WEB_DIR/dist"/ "$REMOTE_HOST:$SHARE_WEB_REMOTE_DIR/"
  ssh "$REMOTE_HOST" "chown -R root:root '$SHARE_WEB_REMOTE_DIR' && find '$SHARE_WEB_REMOTE_DIR' -type d -exec chmod 755 {} \\; && find '$SHARE_WEB_REMOTE_DIR' -type f -exec chmod 644 {} \\;"
fi

# ========== 7. 代码打包并上传到远程 ==========
# 如果启用 rsync 且本地安装了 rsync，使用 rsync 同步
if [[ "$USE_RSYNC" == "1" ]] && command -v rsync >/dev/null 2>&1; then
  RSYNC_DIR="$UPLOAD_DIR/rsync_${TS}"
  # 同步代码到远程临时目录
  rsync -az --delete "${EXCLUDES[@]}" "$SRC_DIR"/ "$REMOTE_HOST:$RSYNC_DIR/"
  # 在远程将同步后的代码打包成压缩包，并删除临时目录
  ssh "$REMOTE_HOST" "cd '$RSYNC_DIR' && tar -czf '$UPLOAD_DIR/$PKG_NAME' . && rm -rf '$RSYNC_DIR'"
else
  # 不使用 rsync：本地先打包，再上传到服务器
  export COPYFILE_DISABLE=1
  TAR_BIN="tar"
  # 如果有 gtar 则使用 gtar（兼容 macOS）
  command -v gtar >/dev/null 2>&1 && TAR_BIN="gtar"
  # 本地打包项目代码
  "$TAR_BIN" -czf "$PKG_PATH" "${EXCLUDES[@]}" -C "$SRC_DIR" .
  # 生成校验和文件，用于验证文件完整性
  shasum -a 256 "$PKG_PATH" | awk '{print $1}' > "$PKG_PATH.sha256"
  # 上传压缩包和校验文件到远程
  scp "$PKG_PATH" "$PKG_PATH.sha256" "$REMOTE_HOST:$UPLOAD_DIR/"
fi

# ========== 8. 在远程执行部署 ==========
# 执行远程部署脚本，传入包路径和环境变量
ssh "$REMOTE_HOST" "PIP_INDEX_URL='$PIP_INDEX_URL' SPARK_BASE='$REMOTE_BASE' bash '$REMOTE_DEPLOY' '$UPLOAD_DIR/$PKG_NAME'"

# 部署完成提示
echo "SparkService deployed: $TS"
