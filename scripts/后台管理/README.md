# TravelDiary 本地启停

在项目根目录执行：

```bash
./scripts/start.sh                 # API + 管理后台 + Celery Worker + Beat + 启用的手帐处理 Worker
./scripts/status.sh                # 查看进程状态
./scripts/restart.sh               # 检查环境后重启
./scripts/stop.sh                  # 停止本项目记录的进程
./scripts/start.sh --check         # 只检查环境、迁移状态和 Redis
./scripts/start.sh --no-frontend   # 不启动管理后台
./scripts/start.sh --no-async      # 不启动异步处理进程，不检查 Redis
```

首次准备 Python `.venv`、安装 `requirements.txt`，在 `backoffice-web` 执行 `pnpm install --frozen-lockfile`，配置根目录 `.env`，启动数据库和 Redis，然后执行 `python manage.py migrate`。启动脚本不自动安装依赖、不执行数据库迁移，也不启停共享数据库或 Redis。

API 默认地址为 `http://127.0.0.1:2026/`，管理后台为 `http://localhost:6018/`。可通过 `BACKEND_HOST`、`BACKEND_PORT`、`FRONTEND_HOST`、`FRONTEND_PORT`、`VENV_PYTHON`、`DJANGO_SETTINGS_MODULE` 覆盖本地配置。管理后台直接运行已安装的 Vite，端口冲突会报错，不会自动换端口。

Worker 只从当前 `CELERY_TASK_ROUTES` 读取所需队列；本地使用 solo pool。Beat 使用数据库调度器。账号验证码和异步操作需要正常运行的 Redis 和 Worker；`--no-async` 适用于单独调试 HTTP/页面的场景。

所有进程 PID 存在 `run/`，与后台异步任务管理页面共用 Worker/Beat PID 文件；日志写入 `logs/<服务名>.stdout.log` 和 `.stderr.log`。服务名为 `backend`、`frontend`、`celery_worker`、`celery_beat`、`preset_processor`。旧脚本留下的 backend/frontend PID 文件也可识别。

停止时核对 PID 的命令属于本项目，并发送退出信号；不按端口或全局进程名清理其他服务。开发 API 使用 `--noreload` 以保持进程归属明确，修改 Python 代码后执行重启。

本脚本用于本地开发。生产部署由部署脚本及仓库外服务器模板负责。

手帐 ZIP 使用独立的 `preset_processor` 进程，不是 Celery 任务。本机 `.env` 配置 `DIARY_PRESETS_LOCAL_PROCESSOR_ENABLED=true`、随机生成的 `DIARY_PRESETS_PROCESSOR_TOKEN`（API 与处理进程共用），以及现有 `ALIYUN_ACCESS_KEY_ID/SECRET`、`ALIYUN_OSS_BUCKET/ENDPOINT`。`PRESET_CONTROL_URL` 默认 `http://127.0.0.1:2026`，端口可随 `BACKEND_PORT` 覆盖。本机通过 OSS 公网 endpoint 处理；生产仍可关闭本机托管，独立部署 OSS 同区域 Worker。

启用后，启动/停止/重启脚本以及后台“异步任务管理”的一键启停均包含手帐处理进程，PID 为 `run/preset_processor.pid`，日志为 `logs/preset_processor.stdout.log`、`logs/preset_processor.stderr.log`。页面同时显示实际控制 API 通信心跳、排队/处理中数量和配置/连接错误；仅有 PID 不算就绪。已上传的 queued 任务会自动领取，无需重新上传；通过校验后按原任务设置直接发布。


### 统一手帐资源队列（2026-10-20）

只保留一个“手帐资源处理 Worker”（`preset_processor`），通过现有一键启停管理。公共手帐 ZIP、专属定制交付 ZIP 同时进入 `diary_presets.ResourceTask` 一张持久化队列表，按入队顺序领取；任务管理只显示统一的排队数和处理中数，不运行单独的专属定制 Worker。用户照片不入队。

升级顺序：停止旧 `preset_processor` → `python manage.py migrate`（含 `diary_presets/0003_resourcetask`，自动迁入存量任务）→ 启动原来的 `preset_processor`。本机可用 `python scripts/runtime.py stop preset_processor` / `python scripts/runtime.py start preset_processor`。生产环境在有 OSS 带宽的同地域工作机运行一个 `python worker.py` 容器，API 主机只登记和调度任务。

处理完成后，公共手帐沿用原发布行为；专属定制只生成待验收候选，需要管理员逐版验收并手动正式交付。
