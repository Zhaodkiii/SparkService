#!/usr/bin/env python3
"""Local process lifecycle for the retained TravelDiary services."""
import argparse
import importlib
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / 'run'
LOG = ROOT / 'logs'
NAMES = ('backend', 'frontend', 'celery_worker', 'celery_beat')
CHILDREN = {}


def pid_paths(name):
    paths = [RUN / f'{name}.pid']
    if name in ('backend', 'frontend'):
        paths.append(ROOT / 'scripts/后台管理/.pids' / f'{name}.pid')
    return paths


def pid_for(name):
    fallback = None
    for path in pid_paths(name):
        try:
            pid = int(path.read_text().strip())
            if owned(pid):
                return pid
            fallback = pid
        except (OSError, ValueError):
            continue
    return fallback


def owned(pid):
    if not pid or pid <= 1:
        return False
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
    return result.returncode == 0 and str(ROOT) in result.stdout


def settings():
    return importlib.import_module(os.environ.get('DJANGO_SETTINGS_MODULE', 'SparkService.settings'))


def queues():
    config = settings()
    names = [config.CELERY_TASK_DEFAULT_QUEUE]
    names.extend(route['queue'] for route in config.CELERY_TASK_ROUTES.values() if isinstance(route, dict) and route.get('queue'))
    return ','.join(dict.fromkeys(names))


def check_port(port):
    try:
        with socket.create_connection(('localhost', port), timeout=0.2):
            return True
    except OSError:
        return False


def command(name):
    python = os.environ.get('VENV_PYTHON', str(ROOT / '.venv/bin/python'))
    if name == 'backend':
        return [python, str(ROOT / 'manage.py'), 'runserver', f"{os.environ.get('BACKEND_HOST', '127.0.0.1')}:{os.environ.get('BACKEND_PORT', '2026')}", '--noreload']
    if name == 'frontend':
        return ['node', str(ROOT / 'backoffice-web/node_modules/vite/bin/vite.js'), str(ROOT / 'backoffice-web'), '--host', os.environ.get('FRONTEND_HOST', 'localhost'), '--port', os.environ.get('FRONTEND_PORT', '6018'), '--strictPort']
    base = [python, '-m', 'celery', '--workdir', str(ROOT), '-A', 'SparkService']
    if name == 'celery_worker':
        return base + ['worker', '--loglevel=INFO', '--pool=solo', '--queues', queues()]
    return base + ['beat', '--loglevel=INFO', '--scheduler', 'django_celery_beat.schedulers:DatabaseScheduler']


def stop(name):
    pid = pid_for(name)
    if owned(pid):
        # Only signal our own process group; never kill arbitrary listeners by port.
        target_group = os.getpgid(pid) == pid
        def send(sig):
            try:
                os.killpg(pid, sig) if target_group else os.kill(pid, sig)
            except ProcessLookupError:
                pass
        send(signal.SIGTERM)
        for _ in range(40):
            if not owned(pid):
                break
            time.sleep(0.25)
        if owned(pid):
            send(signal.SIGKILL)
        child = CHILDREN.pop(pid, None)
        if child is not None:
            child.wait(timeout=5)
        print(f'{name}: 已停止')
    else:
        print(f'{name}: 未运行（或 PID 已失效）')
    for path in pid_paths(name):
        path.unlink(missing_ok=True)


def start(name):
    if owned(pid_for(name)):
        print(f'{name}: 已在运行')
        return
    port = int(os.environ.get('BACKEND_PORT', '2026')) if name == 'backend' else int(os.environ.get('FRONTEND_PORT', '6018')) if name == 'frontend' else None
    if port and check_port(port):
        raise RuntimeError(f'{name}: 端口 {port} 已占用，请检查占用者或更换端口')
    RUN.mkdir(exist_ok=True)
    LOG.mkdir(exist_ok=True)
    with (LOG / f'{name}.stdout.log').open('ab') as out, (LOG / f'{name}.stderr.log').open('ab') as err:
        proc = subprocess.Popen(command(name), cwd=ROOT, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
    CHILDREN[proc.pid] = proc
    (RUN / f'{name}.pid').write_text(str(proc.pid))
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f'{name}: 启动退出，请查看 logs/{name}.stderr.log')
            if port and check_port(port):
                break
            if not port and time.monotonic() > deadline - 18:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(f'{name}: 启动超时，请查看 logs/{name}.stderr.log')
    except BaseException:
        stop(name)
        raise
    print(f'{name}: 已启动，PID={proc.pid}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'check-broker', 'queues'])
    parser.add_argument('name', nargs='?', choices=NAMES)
    args = parser.parse_args()
    if args.action == 'queues':
        print(queues())
    elif args.action == 'check-broker':
        import redis
        client = redis.Redis.from_url(settings().CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
        try:
            client.ping()
        finally:
            client.close()
        print('Redis: 连接正常')
    elif args.action == 'status':
        for name in NAMES:
            pid = pid_for(name)
            print(f'{name}: ' + (f'运行中 PID={pid}' if owned(pid) else '未运行'))
    elif not args.name:
        parser.error('start/stop requires a service name')
    elif args.action == 'start':
        start(args.name)
    else:
        stop(args.name)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'错误: {exc}', file=sys.stderr)
        sys.exit(1)
