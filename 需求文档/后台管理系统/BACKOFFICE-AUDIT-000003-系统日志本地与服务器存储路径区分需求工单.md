# 系统日志本地与服务器存储路径区分需求工单

**工单号**：`BACKOFFICE-AUDIT-000003`

**文档版本**：V1.0

**文档状态**：需求讨论/设计中

**最后更新**：2026-07-30

**适用项目**：SparkService、backoffice、backoffice-web、2026 部署模板

**关联工单**：`BACKOFFICE-AUDIT-000001`、`BACKOFFICE-AUDIT-000002`

> 范围说明：本文只创建新的需求工单，明确系统日志在本地开发、Docker 容器内、服务器宿主机上的目录差异，以及后台系统日志查询应如何识别和展示。本文不修改任何项目代码。

---

## 工单索引

| 工单号 | 工单名 | 状态 | 范围 |
| --- | --- | --- | --- |
| `BACKOFFICE-AUDIT-000003` | 系统日志本地与服务器存储路径区分 | 需求讨论/设计中 | `LOG_ROOT` 运行时识别、本地/容器/宿主机路径映射、后台展示、排障命令、验收 |

---

# 一、背景与问题

## 1.1 问题背景

SparkService 的 Django 日志配置使用：

```python
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_ROOT = Path(os.getenv("LOG_ROOT", BASE_DIR / "logs"))
LOG_DIR = LOG_ROOT / os.getenv("LOG_DATE", "")
```

这意味着：

1. 本地开发如果没有设置 `LOG_ROOT`，日志会写到项目根目录下的 `logs/YYYY-MM-DD/`。
2. 服务器 Docker 部署会设置 `LOG_ROOT=/app/logs`。
3. Docker Compose 把宿主机 `./shared/logs` 挂载到容器内 `/app/logs`。

因此服务器上不能按：

```text
/root/2026/current/logs/YYYY-MM-DD/
```

查找日志。正确宿主机目录是：

```text
/root/2026/shared/logs/YYYY-MM-DD/
```

容器内路径是：

```text
/app/logs/YYYY-MM-DD/
```

## 1.2 现有误区

因为代码目录位于：

```text
/root/2026/current
```

容易误判日志在：

```text
/root/2026/current/logs
```

但生产部署模板中 `docker-compose.yml` 已明确：

```yaml
environment:
  LOG_ROOT: /app/logs

volumes:
  - ./shared/logs:/app/logs
```

所以宿主机真实日志目录是：

```text
/root/2026/shared/logs
```

# 二、路径规则

## 2.1 本地开发环境

未设置 `LOG_ROOT` 时：

```text
项目根目录/logs/YYYY-MM-DD/*.log
```

示例：

```text
/Users/hua/Documents/project/Reference/SparkService/logs/2026-07-30/access.log
```

来源：

```python
LOG_ROOT = Path(os.getenv("LOG_ROOT", BASE_DIR / "logs"))
```

## 2.2 服务器容器内环境

Docker Compose 明确设置：

```text
LOG_ROOT=/app/logs
```

所以 Django 运行时看到：

```text
/app/logs/YYYY-MM-DD/*.log
```

示例：

```text
/app/logs/2026-07-30/access_api_io.log
```

## 2.3 服务器宿主机环境

Docker Compose 挂载：

```text
./shared/logs:/app/logs
```

服务器部署根目录：

```text
/root/2026
```

所以宿主机真实目录：

```text
/root/2026/shared/logs/YYYY-MM-DD/*.log
```

示例：

```text
/root/2026/shared/logs/2026-07-30/access_api_io.log
```

## 2.4 路径映射表

| 环境 | Django `settings.LOG_ROOT` | 宿主机/本机真实目录 | 说明 |
| --- | --- | --- | --- |
| 本地开发 | `BASE_DIR / "logs"` | `/Users/hua/Documents/project/Reference/SparkService/logs` | 未设置 `LOG_ROOT` 时 |
| 服务器容器内 | `/app/logs` | 容器内 `/app/logs` | Django 运行时路径 |
| 服务器宿主机 | `/app/logs` | `/root/2026/shared/logs` | Docker volume 映射到宿主机 |

# 三、产品需求

## 3.1 后台系统日志查询路径原则

后台系统日志查询必须以运行时：

```python
settings.LOG_ROOT
```

为唯一日志根目录。

不得硬编码：

```text
/root/2026/current/logs
/root/2026/shared/logs
/Users/hua/Documents/project/Reference/SparkService/logs
```

原因：

1. Django 在容器内运行时只知道 `/app/logs`。
2. `/app/logs` 已由 Docker volume 映射到宿主机 `/root/2026/shared/logs`。
3. 本地和生产路径不同，硬编码会导致其中一个环境失效。

## 3.2 后台页面展示要求

系统日志页面建议展示当前运行时日志根目录，用于排障：

```text
当前日志根目录：/app/logs
当前查询日期：2026-07-30
当前日志文件：/app/logs/2026-07-30/access_api_io.log
```

如果是生产环境，可在说明文案中展示宿主机映射提示：

```text
生产宿主机路径通常为 /root/2026/shared/logs/YYYY-MM-DD/
```

注意：后台接口返回的真实路径应谨慎处理。若不希望暴露完整服务器路径，可以只返回：

```json
{
  "log_root": "/app/logs",
  "date": "2026-07-30",
  "file": "access_api_io.log"
}
```

## 3.3 系统日志模块接口增强

`GET /api/admin/v1/audit/system-log-modules/` 建议补充：

```json
{
  "log_root": "/app/logs",
  "date_pattern": "YYYY-MM-DD",
  "host_path_hint": "/root/2026/shared/logs",
  "items": [
    {
      "value": "accounts_api_io",
      "label": "账号 API IO",
      "file": "access_api_io.log"
    }
  ]
}
```

`host_path_hint` 可选，建议由环境变量配置：

```text
LOG_HOST_PATH_HINT=/root/2026/shared/logs
```

本地开发可为空。

# 四、技术方案

## 4.1 后端路径解析

系统日志服务只使用：

```python
Path(settings.LOG_ROOT).resolve()
```

示例：

```python
from pathlib import Path
from django.conf import settings
from common.exceptions import APIError


def get_log_root() -> Path:
    return Path(settings.LOG_ROOT).resolve()


def resolve_log_file(*, date: str, filename: str) -> Path:
    root = get_log_root()
    path = (root / date / filename).resolve()
    if root != path and root not in path.parents:
        raise APIError("invalid_log_path", code=40073, status_code=400)
    return path
```

## 4.2 禁止路径猜测

实现时不得根据 `BASE_DIR` 猜测生产日志目录：

```python
# 禁止
BASE_DIR / "logs"
Path("/root/2026/current/logs")
Path("/root/2026/shared/logs")
```

正确方式：

```python
Path(settings.LOG_ROOT)
```

## 4.3 环境变量建议

在 `.deploy.env.example` 中可新增说明型变量：

```text
# 容器内日志根目录，Django 实际使用
LOG_ROOT=/app/logs

# 可选：宿主机日志目录提示，仅用于后台页面说明，不参与文件读取
LOG_HOST_PATH_HINT=/root/2026/shared/logs
```

注意：

1. `LOG_ROOT` 参与 Django 读写。
2. `LOG_HOST_PATH_HINT` 只用于页面提示。
3. 后端文件读取不能使用 `LOG_HOST_PATH_HINT`。

## 4.4 Docker Compose 配置依据

当前服务器模板：

```yaml
services:
  web:
    environment:
      LOG_ROOT: /app/logs
    volumes:
      - ./shared/logs:/app/logs

  celery_worker:
    environment:
      LOG_ROOT: /app/logs
    volumes:
      - ./shared/logs:/app/logs

  celery_beat:
    environment:
      LOG_ROOT: /app/logs
    volumes:
      - ./shared/logs:/app/logs
```

因此 Web、Celery worker、Celery beat 的业务日志都应归档到同一宿主机目录：

```text
/root/2026/shared/logs
```

## 4.5 日志文件示例

按日期目录：

```text
/root/2026/shared/logs/2026-07-30/app.log
/root/2026/shared/logs/2026-07-30/access.log
/root/2026/shared/logs/2026-07-30/access_api_io.log
/root/2026/shared/logs/2026-07-30/celery.log
/root/2026/shared/logs/2026-07-30/chat_sync.log
/root/2026/shared/logs/2026-07-30/chat_sync_api_io.log
/root/2026/shared/logs/2026-07-30/medical_flow.log
/root/2026/shared/logs/2026-07-30/medical_api_io.log
/root/2026/shared/logs/2026-07-30/nutrition_api_io.log
/root/2026/shared/logs/2026-07-30/file_manager.log
/root/2026/shared/logs/2026-07-30/notification_center.log
```

# 五、服务器排障命令

## 5.1 宿主机查看日志

```bash
cd /root/2026
ls -lah shared/logs
ls -lah shared/logs/$(date +%F)
```

## 5.2 查 Apple 登录失败

```bash
grep -R "device_credential_not_registered" -n /root/2026/shared/logs/$(date +%F)
grep -R "/api/v1/auth/apple/login/" -n /root/2026/shared/logs/$(date +%F)
grep -R "9D37AA5E-8CCF-411E-A5C9-C802740C1826" -n /root/2026/shared/logs/$(date +%F)
```

## 5.3 容器内确认运行时路径

```bash
cd /root/2026
docker compose exec web sh -lc 'python manage.py shell -c "from django.conf import settings; print(settings.BASE_DIR); print(settings.LOG_ROOT); print(settings.LOG_DIR)"'
```

预期输出类似：

```text
/app
/app/logs
/app/logs/2026-07-30
```

## 5.4 确认 Docker volume

```bash
cd /root/2026
docker compose config | grep -A4 -n "LOG_ROOT"
docker compose config | grep -A4 -n "shared/logs"
```

# 六、后台页面验收标准

## 6.1 本地环境

1. 本地未配置 `LOG_ROOT` 时，系统日志查询读取：

```text
SparkService/logs/YYYY-MM-DD/
```

2. 页面模块接口返回或内部使用的 `log_root` 为本地项目 `logs` 目录。

## 6.2 服务器环境

1. 服务器容器内 `settings.LOG_ROOT` 为：

```text
/app/logs
```

2. 宿主机真实目录为：

```text
/root/2026/shared/logs
```

3. 后台系统日志页面可以查询当天：

```text
/app/logs/YYYY-MM-DD/access_api_io.log
```

4. 在服务器宿主机上可以通过：

```text
/root/2026/shared/logs/YYYY-MM-DD/access_api_io.log
```

找到同一份文件。

## 6.3 错误路径防护

1. 后台不应尝试读取：

```text
/root/2026/current/logs
```

2. 当日期目录不存在时，接口返回空列表或明确的空状态，不返回 500。
3. 路径校验必须确保最终文件位于 `settings.LOG_ROOT` 下。

# 七、关联文档更新建议

后续可同步更新：

| 文档 | 建议 |
| --- | --- |
| `LOGGING.md` | 增加本地/容器/宿主机路径映射说明 |
| `2026/README.md` | 增加业务日志路径 `/root/2026/shared/logs/YYYY-MM-DD/` |
| `BACKOFFICE-AUDIT-000001` | 引用本工单作为路径差异说明 |
| `BACKOFFICE-AUDIT-000002` | 查询日期控件说明引用本工单 |

# 八、实施备注

1. 本工单不要求变更日志写入逻辑。
2. 本工单不要求迁移历史日志。
3. 本工单重点是防止系统日志查询实现硬编码错误路径。
4. 生产宿主机路径仅用于运维定位；应用内读取应始终使用容器内 `settings.LOG_ROOT`。

