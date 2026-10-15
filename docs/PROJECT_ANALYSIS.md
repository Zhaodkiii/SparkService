# SparkService 项目分析

## 项目定位

SparkService 是面向健康管理产品的后端与配套 Web 应用。它提供账号与认证、医疗档案、营养管理、任务提醒、文件存储、订阅、内容分享和 AI 对话等服务。项目名中的 Spark 指产品名称；从仓库结构看，它不是 Apache Spark 数据处理项目。

## 技术构成

- **后端：** Django、Django REST Framework、SimpleJWT。HTTP API 统一挂载在 `/api/v1/`，后台 API 位于 `/api/admin/v1/`。
- **实时与异步：** Django Channels 提供 WebSocket；Celery 处理 AI 对话、通知、账号注销等后台任务；Redis 同时承担消息代理、结果存储和 Channels 层的支持。
- **数据库：** 默认使用 MySQL，开发环境可以通过 `DB_ENGINE` 切换数据库。配置从根目录 `.env` 和进程环境变量读取。
- **前端：** `chat-web` 是 Next.js/React AI 对话应用；`backoffice-web` 是 Vue 3/Vite 管理后台；`open-web` 是 Vue 3/Vite 的内容及公开分享站点。
- **外部服务：** 配置涵盖阿里云 OSS/STS 和短信、APNs、SMTP、Apple 登录、RevenueCat 订阅同步及兼容 OpenAI 的模型服务。

## 主要业务模块

| 模块 | 主要职责 |
| --- | --- |
| `accounts` | 用户身份、设备与 Web 会话、OTP、Apple 登录、账号注销和访问限制 |
| `medical` | 成员健康档案、就诊、检查、用药、指标、共享与邀请 |
| `nutrition` | 饮食记录、食物、食谱、能量消耗及营养目标 |
| `task_system` | 医疗、运动、饮食等任务、执行记录和通知 |
| `chat_sync` | 跨端会话和消息同步、服务端 AI 对话、工具调用、知识库与记忆 |
| `ai_config` | AI 模型、场景及服务端模型绑定配置 |
| `file_manager` | 文件接口、OSS 对象存储及客户端临时凭证 |
| `content` | 内容文章和公开内容服务 |
| `subscriptions` | RevenueCat webhook、权益和订阅归属同步 |
| `backoffice` | 管理接口及其角色、权限控制 |

## AI 对话架构

`chat_sync` 是技术复杂度最高的部分。对外提供会话同步 API 和 AI Run API；核心状态存储在 `ChatRun`、`ChatRunEvent`、`ChatEventOutbox`、消息及消息块等模型中。Run 使用幂等键和请求哈希避免重复提交，并用显式状态转换管理排队、执行、等待用户输入/客户端工具和结束状态。

请求通常由 API 层创建并持久化，再交给 Celery 的 `chat.ai` 队列执行。事件先写入 Outbox，再由 `chat.events` 队列转发给 WebSocket 订阅者；`chat.recovery` 队列负责过期 Run 与交互的恢复和清理。模型适配、上下文构建、能力注册、工具执行和事件流分别位于 `ai_runtime` 与 `ai_services`，Web 客户端消费统一的消息块与事件契约。该设计把数据库中的持久状态作为事实来源，WebSocket 用于及时通知。

一个重要运行条件是 `CHAT_AI_SERVER_RUNS_ENABLED` 默认值为 `false`。即使 API 服务启动，未开启该开关时服务端 Run 仍会返回禁用错误。部署还需要正确启动相应 Celery 队列、Beat、Redis 和 ASGI/WebSocket 服务。

## 启动与部署线索

仓库提供 `scripts/start.sh`、`scripts/restart.sh`、`scripts/stop.sh` 和 `scripts/后台管理/` 下的启动脚本。管理后台 README 记录的本地入口为 API `127.0.0.1:2026`、管理前端 `localhost:6018`、开放前端 `localhost:2028`；`chat-web` 自身开发端口为 `9001`。部署行为最终应以脚本和环境变量为准，README 中的开发者路径可能过时。

后端依赖列于 `requirements.txt`；各前端分别维护自己的 `package.json`。仓库包含大量 Django 测试、AI 运行时测试和 Web 合约测试，但缺少根目录统一的开发者总览文档。

## 工程特点与关注点

1. **业务面广、部署组件多。** 后端同时承载健康数据、账号、订阅和 AI 对话；上线问题往往跨越数据库、Redis、Celery、ASGI 与多个前端，建议维护一份从全新环境开始的部署与队列检查清单。
2. **AI 对话有较清晰的持久化边界。** Run、事件、消息块、幂等和恢复机制比单纯的请求内同步调用更适合流式与跨端场景；修改时要同步检查事件顺序、重放语义和状态转换。
3. **健康数据与身份授权是高影响区域。** 医疗档案和分享涉及成员绑定、访问范围及软删除；账号登录涉及多端身份别名、设备访客账号和独立 Web 会话。相关变更应检查对象级授权与跨账号隔离。
4. **配置和密钥管理需要持续审视。** 大多数第三方凭证通过环境变量读取，部署时应确保 `.env` 不进入版本控制、生产密钥不回退到开发默认值，并检查 DEBUG、ALLOWED_HOSTS、CORS、HTTPS 与 Cookie 设置。配置允许 `ALLOWED_HOSTS=*` 的默认值，应由生产环境显式覆盖。
5. **前后端契约需要保持同步。** AI 消息块和流事件已有独立契约与校验脚本，跨端改动应同时检查后端序列化、Web 消费逻辑及契约测试。
6. **仓库工作区当前已有其他未提交改动。** 本次分析文档应作为独立提交，避免混入账号、医疗绑定、迁移、日志或 Finder 元数据变更。

## 推荐阅读顺序

1. `SparkService/urls.py` 和 `SparkService/settings.py`：入口、数据库、认证、CORS、异步队列及安全配置。
2. `accounts/models.py` 与 `accounts/auth/`：理解用户身份及登录边界。
3. `medical/models.py`、`medical/services/`：理解成员数据和授权关系。
4. `chat_sync/ai_api/urls.py`、`chat_sync/ai_services/run_service.py`、`chat_sync/ai_models/run.py`：理解 AI Run 生命周期。
5. `SparkService/asgi.py`、`SparkService/celery.py` 和 Celery 任务路由配置：理解实时事件与后台执行。
6. 各前端的入口和 API 客户端：理解客户端怎样消费后端契约。
