from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
import subprocess
import sys


class Command(BaseCommand):
    help = "使用 Daphne 启动 ASGI 服务（同时支持 HTTP 与 WebSocket）"

    def add_arguments(self, parser):
        parser.add_argument("--host", default="0.0.0.0", help="监听地址，默认 0.0.0.0")
        parser.add_argument("--port", type=int, default=8000, help="监听端口，默认 8000")

    def handle(self, *args, **options):
        host = options["host"]
        port = options["port"]
        asgi_setting = settings.ASGI_APPLICATION
        if ":" in asgi_setting:
            asgi_app = asgi_setting
        else:
            module_path, attr = asgi_setting.rsplit(".", 1)
            asgi_app = f"{module_path}:{attr}"

        cmd = [
            sys.executable,
            "-m",
            "daphne",
            "-b",
            host,
            "-p",
            str(port),
            asgi_app,
        ]
        self.stdout.write(self.style.SUCCESS(f"启动 ASGI 服务: {' '.join(cmd)}"))

        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError as exc:
            raise CommandError("未安装 daphne。请先安装依赖后重试（pip install daphne）。") from exc
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"ASGI 服务启动失败，退出码: {exc.returncode}") from exc
