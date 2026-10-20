"""Local processor configuration and health, without exposing credentials."""
import json
import time
from pathlib import Path


def configuration_error(config):
    required = ('DIARY_PRESETS_PROCESSOR_TOKEN', 'ALIYUN_ACCESS_KEY_ID',
                'ALIYUN_ACCESS_KEY_SECRET', 'ALIYUN_OSS_BUCKET', 'ALIYUN_OSS_ENDPOINT')
    missing = [key for key in required if not getattr(config, key, '')]
    return '手帐资源处理缺少配置：' + '、'.join(missing) if missing else ''


def runtime_status():
    from django.conf import settings
    from django.db.models import Count
    from scripts import runtime
    from .models import ResourceTask
    from .resource_queue import eligible

    enabled = settings.DIARY_PRESETS_LOCAL_PROCESSOR_ENABLED
    pid = runtime.pid_for('preset_processor')
    running = runtime.owned(pid)
    heartbeat = {}
    try:
        heartbeat = json.loads((Path(settings.BASE_DIR) / 'run/preset_processor.health.json').read_text())
    except (OSError, ValueError):
        pass
    fresh = (heartbeat.get('pid') == pid and
             0 <= time.time() - heartbeat.get('updated_at', 0) < 120)
    error = configuration_error(settings) if enabled else ''
    compatible = heartbeat.get('protocol_version') == 3
    healthy = running and fresh and compatible and bool(heartbeat.get('connected')) and not error
    counts = dict(ResourceTask.objects.filter(eligible()).values('status').annotate(count=Count('id')).values_list('status', 'count'))
    return dict(enabled=enabled, pid=pid if running else None, running=running,
                healthy=healthy, connected=bool(healthy),
                error=error or ('Worker 仍是旧版本，请重启手帐资源处理 Worker 以启用统一资源队列' if running and fresh and not compatible else heartbeat.get('error', '') if fresh else
                               '处理进程未运行或心跳已过期' if enabled else ''),
                queued=counts.get('queued', 0), processing=counts.get('processing', 0),
                current_scope=heartbeat.get('current_scope') if fresh else None,
                last_seen=heartbeat.get('updated_at') if fresh else None,
                current_job=heartbeat.get('current_job') if fresh else None)
