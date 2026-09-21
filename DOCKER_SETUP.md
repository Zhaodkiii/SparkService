# SparkService Docker 部署指南（本机数据库版本）

## 前置要求

✅ **本机服务必须运行：**
- MySQL 8.0+ (默认 localhost:3306)
- Redis 7.0+ (默认 localhost:6379)

## 快速开始

### 1. 验证本机服务

```bash
# 检查 MySQL
mysql -u root -p -e "SELECT VERSION();"

# 检查 Redis
redis-cli ping
# 返回 PONG 表示正常
```

### 2. 构建 Docker 镜像

```bash
cd /Users/hua/Documents/project/Reference/SparkService
docker build -t sparkservice:latest .
```

### 3. 启动 Docker Compose

```bash
docker compose up -d
```

**启动的容器：**
- `sparkservice_app` (8000): Django Daphne 服务器
- `sparkservice_celery_worker`: 后台任务处理
- `sparkservice_celery_beat`: 定时任务调度

### 4. 检查服务状态

```bash
docker compose ps
```

### 5. 查看日志

```bash
docker compose logs -f app
```

### 6. 访问应用

- **API**: http://localhost:8000/
- **Django Admin**: http://localhost:8000/admin/
- **WebSocket**: ws://localhost:8000/ws/

---

## 配置说明

### 环境变量

编辑项目根目录的 `.env` 文件修改配置：

```bash
# 数据库配置
DB_HOST=127.0.0.1        # 本机地址
DB_PORT=3306
DB_NAME=sparkservice
DB_USER=root
DB_PASSWORD=你的MySQL密码

# Redis 配置
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
```

**容器内自动转换为 `host.docker.internal`** 以连接本机服务。

### Dockerfile

- **多阶段构建**：编译依赖 → 精简镜像
- **基础镜像**：Python 3.11 Alpine (~150MB)
- **ASGI 服务器**：Daphne（支持 WebSocket）

### docker-compose.yml

只包含应用容器：
- `app`: HTTP/WebSocket 入口
- `celery_worker`: 后台任务（可选）
- `celery_beat`: 定时任务（可选）

---

## 常见操作

### 进入 Django Shell

```bash
docker compose exec app python manage.py shell
```

### 执行数据库迁移

```bash
docker compose exec app python manage.py migrate
```

### 创建超级用户

```bash
docker compose exec app python manage.py createsuperuser
```

### 收集静态文件

```bash
docker compose exec app python manage.py collectstatic --noinput
```

### 查看实时日志

```bash
# Django 应用
docker compose logs -f app

# Celery Worker
docker compose logs -f celery_worker

# Celery Beat
docker compose logs -f celery_beat
```

### 停止所有容器

```bash
docker compose down
```

### 清理容器和卷

```bash
docker compose down -v
```

### 重新构建镜像

```bash
docker compose up --build -d
```

---

## 故障排查

### 连接本地 MySQL 失败

**症状：** `django.db.utils.OperationalError: (2003, "Can't connect to MySQL server on 'host.docker.internal'"`

**解决：**

1. 确认 MySQL 运行中：
   ```bash
   mysql -u root -p -e "SELECT 1;"
   ```

2. 检查 MySQL 绑定地址，编辑 `/etc/mysql/my.cnf` 或 `/usr/local/etc/my.cnf`：
   ```ini
   [mysqld]
   bind-address = 0.0.0.0
   ```

3. 重启 MySQL：
   ```bash
   # macOS (Homebrew)
   brew services restart mysql
   
   # Linux
   sudo systemctl restart mysql
   ```

### 连接本地 Redis 失败

**症状：** `redis.exceptions.ConnectionError: Error -2 connecting to host.docker.internal:6379`

**解决：**

1. 确认 Redis 运行中：
   ```bash
   redis-cli ping
   # 应返回 PONG
   ```

2. 检查 Redis 配置，编辑 `redis.conf`：
   ```conf
   bind 0.0.0.0
   protected-mode no
   ```

3. 重启 Redis：
   ```bash
   # macOS (Homebrew)
   brew services restart redis
   
   # Linux
   sudo systemctl restart redis-server
   ```

### 端口 8000 已被占用

**解决：** 修改 `docker-compose.yml`，修改端口映射：

```yaml
services:
  app:
    ports:
      - "8001:8000"  # 改为 8001
```

然后访问 http://localhost:8001/

### 容器无法启动

```bash
# 查看详细错误日志
docker compose logs app

# 检查容器状态
docker compose ps

# 尝试手动运行
docker compose run --rm app python manage.py migrate
```

---

## 快速参考命令

```bash
# 启动
docker compose up -d

# 停止
docker compose down

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f app

# 进入 Django shell
docker compose exec app python manage.py shell

# 执行迁移
docker compose exec app python manage.py migrate

# 重新构建
docker compose up --build -d

# 清理所有
docker compose down -v
```

---

## 架构图

```
┌─────────────────┐
│   客户端请求    │
└────────┬────────┘
         │ HTTP/WS
         ▼
┌──────────────────────┐
│ Docker Container     │
├──────────────────────┤
│ Django (Daphne)      │
│ 8000 ────────┐       │
│              │       │
│ Celery Worker(可选)  │
│              │       │
│ Celery Beat (可选)   │
└──┬───────────┼───────┘
   │           │
   │ SQL       │ Redis/Celery
   ▼           ▼
┌──────────────┐  ┌──────────────┐
│ MySQL        │  │ Redis        │
│ localhost:   │  │ localhost:   │
│ 3306         │  │ 6379         │
│ (本机)       │  │ (本机)       │
└──────────────┘  └──────────────┘
```

---

## 生产部署注意事项

1. **强 SECRET_KEY**
   ```bash
   python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
   ```

2. **HTTPS 反向代理** (Nginx)
   ```nginx
   location / {
       proxy_pass http://localhost:8000;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
   }
   ```

3. **监控与日志**
   ```bash
   docker compose logs --tail 100 app | grep ERROR
   ```

4. **数据库备份**
   ```bash
   mysqldump -u root -p sparkservice > backup.sql
   ```

---

## 下一步

1. ✅ 确保本机 MySQL 和 Redis 运行中
2. ✅ 运行 `docker compose up -d`
3. ✅ 验证容器状态：`docker compose ps`
4. ✅ 访问 http://localhost:8000
5. ✅ 查看日志：`docker compose logs -f app`
