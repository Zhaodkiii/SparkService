# TravelDiary 本地启停

在项目根目录执行：

```bash
./scripts/start.sh                 # API + 管理后台 + Worker + Beat
./scripts/status.sh                # 查看进程状态
./scripts/restart.sh               # 检查环境后重启
./scripts/stop.sh                  # 停止本项目记录的进程
./scripts/start.sh --check         # 只检查环境、迁移状态和 Redis
./scripts/start.sh --no-frontend   # 不启动管理后台
./scripts/start.sh --no-async      # 不启动 Worker/Beat，不检查 Redis
```

首次准备 Python `.venv`、安装 `requirements.txt`，在 `backoffice-web` 执行 `pnpm install --frozen-lockfile`，配置根目录 `.env`，启动数据库和 Redis，然后执行 `python manage.py migrate`。启动脚本不自动安装依赖、不执行数据库迁移，也不启停共享数据库或 Redis。

API 默认地址为 `http://127.0.0.1:2026/`，管理后台为 `http://localhost:6018/`。可通过 `BACKEND_HOST`、`BACKEND_PORT`、`FRONTEND_HOST`、`FRONTEND_PORT`、`VENV_PYTHON`、`DJANGO_SETTINGS_MODULE` 覆盖本地配置。管理后台直接运行已安装的 Vite，端口冲突会报错，不会自动换端口。

Worker 只从当前 `CELERY_TASK_ROUTES` 读取所需队列；本地使用 solo pool。Beat 使用数据库调度器。账号验证码和异步操作需要正常运行的 Redis 和 Worker；`--no-async` 适用于单独调试 HTTP/页面的场景。

所有进程 PID 存在 `run/`，与后台异步任务管理页面共用 Worker/Beat PID 文件；日志写入 `logs/<服务名>.stdout.log` 和 `.stderr.log`。服务名为 `backend`、`frontend`、`celery_worker`、`celery_beat`。旧脚本留下的 backend/frontend PID 文件也可识别。

停止时核对 PID 的命令属于本项目，并发送退出信号；不按端口或全局进程名清理其他服务。开发 API 使用 `--noreload` 以保持进程归属明确，修改 Python 代码后执行重启。

本脚本用于本地开发。生产部署由部署脚本及仓库外服务器模板负责。
