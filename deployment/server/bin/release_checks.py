"""Validate release configuration without printing credentials."""
import os
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


def validate_config(values):
    errors = []
    for key in ("DJANGO_SECRET_KEY", "DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        if not values.get(key, "").strip():
            errors.append(f"缺少非空配置 {key}")
    for key, expected in (("DB_HOST", "127.0.0.1"), ("DB_NAME", "sparkservice")):
        if values.get(key) != expected:
            errors.append(f"{key} 与 TravelDiary 生产环境不符")
    if values.get("DB_ENGINE", "django.db.backends.mysql") != "django.db.backends.mysql":
        errors.append("DB_ENGINE 必须使用生产 MySQL 后端")
    for key, expected in (("DB_PORT", "3306"), ("DJANGO_PORT", "12026"), ("FRONTEND_PORT", "12018"), ("REDIS_PORT", "6379"), ("REDIS_HOST", "127.0.0.1")):
        if values.get(key, expected) != expected:
            errors.append(f"{key} 与已部署基础设施不符")
    for key, expected in (("DJANGO_ALLOWED_HOSTS", "diary.dreamwhale.top"), ("CSRF_TRUSTED_ORIGINS", "https://diary.dreamwhale.top"), ("CORS_ALLOWED_ORIGINS", "https://diary.dreamwhale.top")):
        if expected not in {item.strip() for item in values.get(key, "").split(",")}:
            errors.append(f"{key} 缺少生产域名")
    if values.get("DJANGO_DEBUG", "false").lower() not in {"0", "false", "no", "n"}:
        errors.append("生产环境不能开启 DJANGO_DEBUG")
    for key in ("CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        try:
            url = urlsplit(values.get(key, ""))
            if url.scheme != "redis" or url.hostname != "127.0.0.1" or (url.port or 6379) != 6379:
                errors.append(f"{key} 必须指向本机 Redis")
        except ValueError:
            errors.append(f"{key} 格式无效")
    queues = {queue.strip() for queue in values.get("CELERY_QUEUES", "").split(",")}
    if queues.intersection({"default", "chat.ai", "chat.events", "chat.recovery", "subscriptions"}):
        errors.append("CELERY_QUEUES 包含已删除队列")
    # 生产必须保持接收端身份；按 settings.py 的布尔解析方式严格检查。
    if values.get("MATERIAL_SYNC_ENVIRONMENT_ID") != "production":
        errors.append("MATERIAL_SYNC_ENVIRONMENT_ID 必须为 production，不能使用本地环境身份")
    if values.get("MATERIAL_SYNC_SOURCE_ENABLED", "false").lower() != "false":
        errors.append("生产 MATERIAL_SYNC_SOURCE_ENABLED 必须为 false")
    if values.get("MATERIAL_SYNC_RECEIVER_ENABLED", "").lower() != "true":
        errors.append("生产 MATERIAL_SYNC_RECEIVER_ENABLED 必须为 true")
    try:
        keys = json.loads(values.get("MATERIAL_SYNC_ACCEPTED_KEYS", "{}"))
        if not isinstance(keys, dict) or not keys:
            raise ValueError()
        for key, record in keys.items():
            if (not isinstance(key, str) or not key.strip() or not isinstance(record, dict)
                    or not isinstance(record.get("environment"), str)
                    or not record["environment"].strip() or record["environment"] == "production"
                    or not isinstance(record.get("secret"), str) or not record["secret"].strip()):
                raise ValueError()
    except (ValueError, TypeError):
        errors.append("MATERIAL_SYNC_ACCEPTED_KEYS 必须配置有效来源身份和配对密钥（不显示密钥内容）")
    if errors:
        raise ValueError("；".join(errors))


def load_config(path):
    from dotenv import dotenv_values
    from dotenv.parser import parse_stream

    with Path(path).open() as stream:
        bindings = list(parse_stream(stream))
    keys = [binding.key for binding in bindings if binding.key]
    if any(binding.error for binding in bindings) or len(keys) != len(set(keys)):
        raise ValueError("环境文件存在语法错误或重复键")
    values = dotenv_values(path, interpolate=False)
    return {key: value or "" for key, value in values.items()}


def check_connections():
    import django
    from django.db import connection
    from django.conf import settings
    from redis import Redis

    django.setup()
    connection.settings_dict["OPTIONS"].update(connect_timeout=5, read_timeout=5, write_timeout=5)
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone()[0] != 1:
            raise RuntimeError("Database probe failed")
    for url in {settings.CELERY_BROKER_URL, settings.CELERY_RESULT_BACKEND}:
        client = Redis.from_url(url, socket_connect_timeout=5, socket_timeout=5)
        try:
            if not client.ping():
                raise RuntimeError("Redis probe failed")
        finally:
            client.close()


def check_workers():
    import django
    from django.conf import settings
    from SparkService.celery import app

    django.setup()
    inspector = app.control.inspect(timeout=5)
    pings = inspector.ping() or {}
    registered = inspector.registered() or {}
    active = inspector.active_queues() or {}
    if not pings:
        raise RuntimeError("Worker 未响应")
    required_tasks = set(settings.CELERY_TASK_ROUTES) | {"ai_config.tasks.approve_trial_application_request_task"}
    required_queues = {settings.CELERY_TASK_DEFAULT_QUEUE} | {route["queue"] for route in settings.CELERY_TASK_ROUTES.values()}
    for worker in pings:
        tasks = set(registered.get(worker, []))
        queues = {queue["name"] for queue in active.get(worker, [])}
        if required_tasks - tasks or required_queues - queues:
            raise RuntimeError("Worker 缺少任务或队列")
        if queues.intersection({"default", "chat.ai", "chat.events", "chat.recovery", "subscriptions"}):
            raise RuntimeError("Worker 消费已删除队列")
        if any(task.startswith(("chat_sync.", "subscriptions.", "medical.", "nutrition.", "task_system.", "content.")) for task in tasks):
            raise RuntimeError("Worker 注册了已删除任务")


def main():
    mode = sys.argv[1]
    if mode == "config":
        try:
            validate_config(load_config(sys.argv[2]))
        except ValueError as error:
            raise SystemExit(str(error)) from None
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SparkService.settings")
        try:
            validate_config(os.environ)
        except ValueError as error:
            # validate_config only reports field names/rules, never credential values.
            raise SystemExit(f"发布检查 {mode} 失败：{error}") from None
        try:
            if mode == "environment":
                pass
            elif mode == "connections":
                check_connections()
            elif mode == "workers":
                check_workers()
            else:
                raise ValueError("Unknown release check")
        except Exception as error:
            raise SystemExit(f"发布检查 {mode} 失败：{type(error).__name__}（请核对配置、数据库授权或 Worker 状态）") from None
    print(f"发布检查通过：{mode}")


if __name__ == "__main__":
    main()
