# TravelDiary 服务端

为 TravelDiaryClient 提供账号、文件和客户端 AI 设置服务，并保留管理后台和异步任务基础设施。

## 保留模块

| 目录 | 职责 |
| --- | --- |
| `accounts` | 密码、Apple、设备游客、手机/邮箱验证码登录，令牌刷新、设备会话、身份绑定、注销及访问控制 |
| `file_manager` | 文件登记、列表、业务绑定、下载和删除，OSS 与 OCR STS 凭证 |
| `ai_config` | 客户端实际调用的模型配置、试用状态/申请及 Provider 连接测试；不执行服务端对话 |
| `notification_center` | 验证码、账号通知及通知投递/回执基础能力 |
| `backoffice`、`backoffice-web` | 用户、设备、权限、审计、通知、AI 配置和异步任务管理 |
| `common` | 响应、异常、日志、请求上下文及权限工具 |

医疗、营养、健康任务、医院、旧数据迁移、文章、订阅、版本检查、服务端聊天、知识库/记忆和两个用户 Web 前端已移除。文件访问和业务附件查询按所有者隔离。

## 本地运行

准备 Python 环境并安装 `requirements.txt`，配置根目录 `.env` 中的数据库、Redis、JWT、Apple、短信、邮箱和 OSS 参数。不要复用旧健康产品的身份命名空间、云资源和密钥配置来部署独立的 TravelDiary 环境。

```bash
python manage.py migrate
./scripts/start.sh
```

API 默认地址为 `http://127.0.0.1:2026/`，管理后台为 `http://localhost:6018/`。管理前端首次使用 pnpm 安装依赖。生产默认 MySQL；ASGI 仅处理 HTTP，不再提供聊天 WebSocket。

`start.sh` 默认同时启动 API、管理后台、Celery Worker 和 Beat。Redis 与数据库需预先启动。支持 `--check`、`--no-frontend`、`--no-async`；通过 `./scripts/status.sh` 查看状态，`./scripts/stop.sh` 停止项目进程。详细说明见 [本地启停](scripts/后台管理/README.md)。

下面是手动运行异步服务的替代命令；使用一键启动后无需再次执行（已启用的手帐资源 Worker 也随一键启动运行，配置见 `scripts/后台管理/README.md`）：

```bash
celery -A SparkService worker -l INFO -Q celery,deactivation,cleanup,monitoring,notification.security.high,notification.bulk,notification.transactional,notification.receipt
celery -A SparkService beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

异步任务保留账号注销、备份清理、健康检查（指注销任务运行状态）、验证码、通知投递/回执与客户端 AI 试用申请处理。

## 升级说明

先停止旧 Worker/Beat，再使用本分支的依赖与代码执行迁移、重启保留的队列。迁移会停用已删除模块的数据库周期任务与后台权限，并退役对应通知场景。原医疗统计迁移编号保留为无操作迁移，以解除对已删除 app 的依赖。

本轮不连接或清空原有业务数据库；旧业务表保留，新代码不再访问。不要把旧健康服务数据库直接作为 TravelDiary 的共享运行库。旧版服务器模板位于仓库外，部署前还需对齐其 Worker 队列、容器、反向代理和依赖；本仓库脚本已移除聊天/开放 Web 的构建上传步骤。

## 验证说明

本地原虚拟环境的 cryptography 二进制存在异常，本轮通过临时依赖目录完成检查。回归测试使用隔离 SQLite 模型建表；现有历史迁移含 MySQL 专用 SQL，完整 MySQL 空库迁移需在独立 MySQL 环境验证。迁移图与模型迁移一致性另行检查。

本轮验证：管理后台构建、Django 系统检查、迁移图和模型迁移一致性通过；166 项保留功能回归与新增的两项升级配置测试通过。完整套件共 266 项，264 项通过，另有两项在原始提交上也可复现的失败：邮箱 OTP 封禁检查，以及登录测试仍断言旧的 `access` 字段。它们不属于本轮裁剪改动，需要单独处理。

运行隔离测试：`python manage.py test --settings=SparkService.test_settings`。该设置不运行历史 MySQL 迁移、不连接生产数据库，关闭真实短信与 APNs 凭证并使用内存邮件和消息代理。

## 发布目标隔离

统一发布入口为 `scripts/deploy_sparkservice.sh`，默认且唯一允许的目标是 `root@39.106.39.110`。**禁止将 TravelDiary 分支发布到 139.196.215.51**；修改环境变量或使用 SSH 别名均不能绕过目标检查。可执行 `bash scripts/deploy_sparkservice.sh --check-target` 做纯本地目标校验。

发布前必须提供实际存在且已适配当前四服务拓扑的 `SERVER_TEMPLATE_DIR`。当前默认的相邻 `2026` 模板目录尚不存在；本轮不执行发布。管理前端默认同域 `/api/`，如使用独立 API 域名应显式设置已核实的 `VITE_API_BASE_URL`，不要沿用旧服务器域名。默认不取消远端已有部署；仅在明确授权后设置 `CANCEL_RUNNING_DEPLOY=1`。

## 当前生产部署

TravelDiary 独立域名为 `https://diary.dreamwhale.top`。宿主机 Nginx 将 `/api/` 和 `/health/` 转发至本机 12026，将管理后台根路径转发至 12018；FRP 的 2026/6018 端口及旧域名保持独立。TLS 证书由 Certbot webroot 签发并自动续期。

服务器模板已纳入 `deployment/server`。生产后端使用 Gunicorn HTTP 服务，四应用服务共享宿主机网络；数据库为该服务器本机 MariaDB 的 sparkservice，专用数据库用户仅有该库权限。旧外部 RDS 地址无法解析，本次没有删除或修改外部 RDS 数据。

一次性清库参数为 `RESET_DATABASE_NAME=sparkservice`，仅在用户明确要求数据库初始化时使用。普通发布不设置此变量。清库会永久删除当前配置应用库的全部数据，脚本同时校验目标 IP 与库名，不自动回滚数据。发布包排除数据库备份、密钥目录、SQL、SQLite、Redis 快照与临时文件。
