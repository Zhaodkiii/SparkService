# TravelDiary 发布记录（2026-10-15）

- 服务器：39.106.39.110，分支 TravelDiary。
- release：`/root/2026/releases/20261015_203954`。
- 域名：`https://diary.dreamwhale.top`，DNS A 指向 39.106.39.110。
- Nginx：`/api/`、`/health/` → 127.0.0.1:12026；根路径后台 → 127.0.0.1:12018。
- 旧域名和 FRP 的 2026/6018 端口未切换。
- TLS：Let's Encrypt，证书到期 2027-01-13，已有每日续期任务和续期重载钩子。
- 后端 Gunicorn、后台 Nginx healthy；Worker 与 Beat running，实际通知任务执行成功。
- 数据库：39 服务器本机 MariaDB，sparkservice 专用用户；应用库空库重建后迁移成功，71 张当前模型所需表、0 个用户，无多余表。
- 原配置的外部阿里云 RDS 无法解析，因此未能删除或修改它；新服务不使用该 RDS。
- Redis 使用独立逻辑库 4（broker）与 5（results）。
- API HTTPS 200，后台 HTTPS 200，未认证账号接口 401，迁移检查通过。
- iOS SupportAppEnvironment 的所有 API 环境更新为新域名，Swift 语法解析通过。
- 发布包已排除本地数据库备份、SQL、密钥目录和临时文件；本次未向 139.196.215.51 连接或发布。
- 未验证真实短信、Apple 登录、OSS/OCR 第三方授权；没有创建测试或管理员用户，以保持用户库为空。
