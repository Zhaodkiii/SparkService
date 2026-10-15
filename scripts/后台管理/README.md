# TravelDiary 本地启停

在项目根目录执行 `./scripts/start.sh`、`./scripts/restart.sh`、`./scripts/stop.sh`。

- Django API：http://127.0.0.1:2026/
- 管理后台：http://localhost:6018/
- 日志：`scripts/后台管理/logs/backend.log` 和 `frontend.log`

启动前需准备 Python 虚拟环境、数据库、Redis 和 pnpm。异步 Worker 与 Beat 按部署配置启动。
