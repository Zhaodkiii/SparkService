# SparkService · 本地一键启停

| 服务 | 地址 |
|------|------|
| Django API | http://127.0.0.1:2026/ |
| 管理前端 | http://localhost:6018/ |
| 开放前端 | http://localhost:2028/ |

## 命令

```bash
cd /Users/hua/Documents/project/Reference/SparkService

./scripts/后台管理/start.sh    # 一键启动
./scripts/后台管理/restart.sh   # 一键重启
./scripts/后台管理/stop.sh      # 停止
```

## 日志

- `scripts/后台管理/logs/backend.log`
- `scripts/后台管理/logs/frontend.log`
- `scripts/后台管理/logs/open-web.log`

开放端内容文章示例：

```text
http://localhost:2028/content/jx9hdj8ickbk0xvb?locale=zh-CN
```
